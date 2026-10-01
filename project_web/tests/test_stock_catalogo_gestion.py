from __future__ import annotations

import re

import pytest
from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-cat"), activo=True, is_admin=False, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-cat", "csrf_token": tok}).status_code in (302, 303)
    return client


def _ingreso(nombre, cantidad, lote):
    from app.services import stock_service

    stock_service.save_ingreso("materia_prima", nombre, "Marca X", "2027-12-31", lote, cantidad, "op",
                               unidad="kg", fecha="2026-09-20", hora="08:00")


def _pid(nombre):
    from app.extensions import db
    from app.models import ProductoCatalogo

    return int(db.session.query(ProductoCatalogo).filter_by(categoria="materia_prima", nombre_producto=nombre).one().id)


def test_lucia_unifica_duplicados_con_stock(app, client):
    from app.extensions import db
    from app.models import IngresoStock, ProductoCatalogo

    with app.app_context():
        _ingreso("Sal fina", 1000.0, "L1")
        _ingreso("Sal Fina Industrial", 500.0, "L2")
        dup, dst = _pid("Sal Fina Industrial"), _pid("Sal fina")

    c = _login(app, client, "pytest_lucia_cat", rol="responsable_laboratorio")
    lista = c.get("/produccion/stock/catalogo").get_data(as_text=True)
    assert f"/produccion/stock/catalogo/{dup}/editar" in lista
    editar = c.get(f"/produccion/stock/catalogo/{dup}/editar").get_data(as_text=True)
    assert "Unificar con otro producto" in editar and "no eliminar" in editar

    r = c.post(f"/produccion/stock/catalogo/{dup}/unificar", data={"destino_id": str(dst)}, follow_redirects=True)
    assert "se unificó en «Sal fina»" in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(ProductoCatalogo, dup).activo is False
        assert db.session.query(IngresoStock).filter_by(producto="Sal Fina Industrial").count() == 0
        ingresos = db.session.query(IngresoStock).filter_by(producto="Sal fina").all()
        assert sorted(i.cantidad for i in ingresos) == [500.0, 1000.0]


def test_lucia_renombra_y_elimina(app, client):
    from app.extensions import db
    from app.models import IngresoStock, ProductoCatalogo
    from app.services import stock_service

    with app.app_context():
        _ingreso("Soda caustica", 200.0, "L3")
        _ingreso("Soda cáustica", 100.0, "L4")
        pid = _pid("Soda caustica")
        stock_service.create_catalog_product("materia_prima", "Producto por error", stock_minimo_alerta=0.0)
        db.session.commit()
        vacio = _pid("Producto por error")

    c = _login(app, client, "pytest_lucia_cat2", rol="responsable_laboratorio")
    # Renombrar a un nombre que ya existe: pide unificar.
    r = c.post(f"/produccion/stock/catalogo/{pid}/editar", data={"nombre_producto": "Soda cáustica", "nueva_categoria": "materia_prima"}, follow_redirects=True)
    assert "usá «Unificar»" in r.get_data(as_text=True)
    r = c.post(f"/produccion/stock/catalogo/{pid}/editar", data={"nombre_producto": "Soda cáustica 50%", "nueva_categoria": "materia_prima", "stock_minimo_alerta": "0"})
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(ProductoCatalogo, pid).nombre_producto == "Soda cáustica 50%"
        assert db.session.query(IngresoStock).filter_by(producto="Soda cáustica 50%").count() == 1

    # Con movimientos no se elimina; sin movimientos sí.
    r = c.post(f"/produccion/stock/catalogo/{pid}/eliminar-definitivo", follow_redirects=True)
    assert "no se puede eliminar" in r.get_data(as_text=True)
    r = c.post(f"/produccion/stock/catalogo/{vacio}/eliminar-definitivo", follow_redirects=True)
    assert "Se eliminó «Producto por error»" in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(ProductoCatalogo, vacio) is None


def test_operador_no_edita_ni_unifica(app, client):
    with app.app_context():
        _ingreso("Ácido test", 10.0, "L5")
        _ingreso("Acido test", 10.0, "L6")
        a, b = _pid("Ácido test"), _pid("Acido test")
    c = _login(app, client, "pytest_oper_cat", rol="operaciones")
    r = c.get(f"/produccion/stock/catalogo/{a}/editar", follow_redirects=True)
    assert "Solo el administrador y el responsable de laboratorio" in r.get_data(as_text=True)
    c.post(f"/produccion/stock/catalogo/{a}/unificar", data={"destino_id": str(b)})
    from app.extensions import db
    from app.models import ProductoCatalogo

    with app.app_context():
        assert db.session.get(ProductoCatalogo, a).activo is True
