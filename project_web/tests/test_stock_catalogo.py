from __future__ import annotations

import re

from werkzeug.security import generate_password_hash


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_quitar_catalogo_hides_product_and_keeps_ingreso(app, auth_client):
    from app.extensions import db
    from app.models import IngresoStock, ProductoCatalogo
    from app.services import stock_service

    with app.app_context():
        stock_service.save_ingreso(
            "laboratorio",
            "Reactivo mal cargado",
            "Marca pytest",
            "2027-12-31",
            "L-ERR-1",
            2.0,
            "admin",
            unidad="L",
            fecha="2026-09-18",
            hora="08:00",
        )
        pid = int(
            db.session.query(ProductoCatalogo)
            .filter_by(categoria="laboratorio", nombre_producto="Reactivo mal cargado")
            .one()
            .id
        )

    page = auth_client.get("/produccion/stock/catalogo")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Reactivo mal cargado" in html
    assert "Quitar" in html

    resp = auth_client.post(
        f"/produccion/stock/catalogo/{pid}/eliminar",
        data={"csrf_token": _csrf(html)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Se quitó «Reactivo mal cargado» del catálogo" in resp.get_data(as_text=True)

    listed = auth_client.get("/produccion/stock/catalogo")
    listed_html = listed.get_data(as_text=True)
    assert "Reactivo mal cargado" not in listed_html

    ingreso = auth_client.get("/produccion/stock/ingreso?categoria=laboratorio")
    assert "Reactivo mal cargado" not in ingreso.get_data(as_text=True)

    with app.app_context():
        row = db.session.get(ProductoCatalogo, pid)
        assert row is not None
        assert row.activo is False
        assert stock_service.list_productos_catalogo_rows("laboratorio") == []
        assert "Reactivo mal cargado" not in stock_service.productos_catalogo("laboratorio")
        assert db.session.query(IngresoStock).filter_by(producto="Reactivo mal cargado").count() == 1


def test_alta_tras_quitar_reactiva_el_mismo_producto(app):
    from app.extensions import db
    from app.models import ProductoCatalogo
    from app.services import stock_service

    with app.app_context():
        stock_service.create_catalog_product(
            "materia_prima",
            "Soda typo",
            stock_minimo_alerta=1.0,
        )
        pid = int(
            db.session.query(ProductoCatalogo)
            .filter_by(categoria="materia_prima", nombre_producto="Soda typo")
            .one()
            .id
        )
        stock_service.deactivate_catalog_product(pid)
        stock_service.create_catalog_product(
            "materia_prima",
            "Soda typo",
            stock_minimo_alerta=5.0,
        )
        same = db.session.get(ProductoCatalogo, pid)
        assert same is not None
        assert same.activo is True
        assert same.stock_minimo_alerta == 5.0
        names = stock_service.productos_catalogo("materia_prima")
        assert names.count("Soda typo") == 1


def test_quitar_catalogo_blocked_without_perm(client, app):
    from app.extensions import db
    from app.models import ProductoCatalogo, User
    from app.services import stock_service

    with app.app_context():
        stock_service.create_catalog_product(
            "materia_prima",
            "Salmuera errada",
            stock_minimo_alerta=0.0,
        )
        pid = int(
            db.session.query(ProductoCatalogo)
            .filter_by(categoria="materia_prima", nombre_producto="Salmuera errada")
            .one()
            .id
        )
        db.session.add(
            User(
                username="pytest_logistica_cat",
                password_hash=generate_password_hash("pw"),
                is_admin=False,
                activo=True,
                rol="logistica",
            )
        )
        db.session.commit()

    lg = client.get("/login")
    html = lg.get_data(as_text=True)
    client.post(
        "/login",
        data={"username": "pytest_logistica_cat", "password": "pw", "csrf_token": _csrf(html)},
        follow_redirects=False,
    )
    page = client.get("/produccion/stock/catalogo", follow_redirects=True)
    assert page.status_code == 200
    listed = page.get_data(as_text=True)
    assert "Salmuera errada" in listed
    assert "Quitar" not in listed
    resp = client.post(
        f"/produccion/stock/catalogo/{pid}/eliminar",
        data={"csrf_token": _csrf(html)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "No tenés permiso para quitar productos de esa categoría." in resp.get_data(as_text=True)
    with app.app_context():
        still = db.session.get(ProductoCatalogo, pid)
        assert still is not None
        assert still.activo is True
