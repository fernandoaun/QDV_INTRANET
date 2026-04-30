from __future__ import annotations

from datetime import date
from io import BytesIO
import re


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _seed_ingreso(app) -> int:
    from app.extensions import db
    from app.models import IngresoStock
    from app.services import stock_service

    with app.app_context():
        stock_service.save_ingreso(
            "materia_prima",
            "Soda ajuste pytest",
            "Marca pytest",
            "2027-12-31",
            "L- AJ-1",
            10.0,
            "admin",
            unidad="kg",
            fecha="2026-04-30",
            hora="08:00",
        )
        row = db.session.query(IngresoStock).filter_by(producto="Soda ajuste pytest").one()
        return int(row.id)


def test_admin_stock_ajuste_changes_stock_without_consumo(app, auth_client):
    from app.extensions import db
    from app.models import ConsumoStock, StockAjuste
    from app.services import stock_service

    ingreso_id = _seed_ingreso(app)

    page = auth_client.get(
        "/produccion/stock/ajustes?categoria=materia_prima&producto=Soda%20ajuste%20pytest&marca=Marca%20pytest"
    )
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Ajustes administrativos de stock" in html

    neg = auth_client.post(
        "/produccion/stock/ajustes",
        data={
            "csrf_token": _csrf(html),
            "categoria": "materia_prima",
            "producto": "Soda ajuste pytest",
            "marca": "Marca pytest",
            "ingreso_stock_id": str(ingreso_id),
            "tipo": "negativo",
            "cantidad": "2",
            "motivo": "Diferencia de inventario",
            "observaciones": "Recuento físico",
        },
    )
    assert neg.status_code in (302, 303)

    with app.app_context():
        assert db.session.query(ConsumoStock).count() == 0
        ajuste = db.session.query(StockAjuste).one()
        assert ajuste.cantidad == -2
        assert stock_service.stock_actual("materia_prima", "Soda ajuste pytest", "Marca pytest") == 8.0
        assert stock_service.consumos_recientes("materia_prima", "Soda ajuste pytest") == []

    page = auth_client.get(
        "/produccion/stock/ajustes?categoria=materia_prima&producto=Soda%20ajuste%20pytest&marca=Marca%20pytest"
    )
    pos = auth_client.post(
        "/produccion/stock/ajustes",
        data={
            "csrf_token": _csrf(page.get_data(as_text=True)),
            "categoria": "materia_prima",
            "producto": "Soda ajuste pytest",
            "marca": "Marca pytest",
            "ingreso_stock_id": str(ingreso_id),
            "tipo": "positivo",
            "cantidad": "3",
            "motivo": "Sobrante detectado",
        },
    )
    assert pos.status_code in (302, 303)
    with app.app_context():
        assert db.session.query(ConsumoStock).count() == 0
        assert db.session.query(StockAjuste).count() == 2
        assert stock_service.stock_actual("materia_prima", "Soda ajuste pytest", "Marca pytest") == 11.0


def test_stock_ajuste_negative_cannot_exceed_available(app, auth_client):
    from app.extensions import db
    from app.models import StockAjuste

    ingreso_id = _seed_ingreso(app)
    page = auth_client.get(
        "/produccion/stock/ajustes?categoria=materia_prima&producto=Soda%20ajuste%20pytest&marca=Marca%20pytest"
    )
    resp = auth_client.post(
        "/produccion/stock/ajustes",
        data={
            "csrf_token": _csrf(page.get_data(as_text=True)),
            "categoria": "materia_prima",
            "producto": "Soda ajuste pytest",
            "marca": "Marca pytest",
            "ingreso_stock_id": str(ingreso_id),
            "tipo": "negativo",
            "cantidad": "99",
            "motivo": "Error",
        },
    )
    assert resp.status_code == 200
    assert "saldo negativo" in resp.get_data(as_text=True)
    with app.app_context():
        assert db.session.query(StockAjuste).count() == 0


def test_stock_ajustes_export(app, auth_client):
    from openpyxl import load_workbook

    from app.services.historicos_export_service import build_historicos_workbook

    ingreso_id = _seed_ingreso(app)
    page = auth_client.get(
        "/produccion/stock/ajustes?categoria=materia_prima&producto=Soda%20ajuste%20pytest&marca=Marca%20pytest"
    )
    resp = auth_client.post(
        "/produccion/stock/ajustes",
        data={
            "csrf_token": _csrf(page.get_data(as_text=True)),
            "categoria": "materia_prima",
            "producto": "Soda ajuste pytest",
            "marca": "Marca pytest",
            "ingreso_stock_id": str(ingreso_id),
            "tipo": "positivo",
            "cantidad": "1.5",
            "motivo": "Ajuste gerencia",
        },
    )
    assert resp.status_code in (302, 303)

    with app.app_context():
        bio, err = build_historicos_workbook(
            ["stock_ajustes"],
            date.fromisoformat("2026-04-30"),
            date.fromisoformat("2026-04-30"),
        )
    assert err is None
    assert bio is not None
    wb = load_workbook(BytesIO(bio.getvalue()))
    ws = wb.active
    assert ws.title == "Stock_ajustes"
    headers = [cell.value for cell in ws[1]]
    assert "Cantidad firmada" in headers
    assert ws.cell(row=2, column=headers.index("Cantidad firmada") + 1).value == 1.5

def test_stock_ajustes_non_admin_blocked(mant_client):
    blocked = mant_client.get("/produccion/stock/ajustes", follow_redirects=False)
    assert blocked.status_code in (302, 303)
