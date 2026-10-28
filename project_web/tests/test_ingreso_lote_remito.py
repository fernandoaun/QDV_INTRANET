"""Ingresos de stock: sin lote se identifican por remito; sin vencimiento, vencen a un año."""
from datetime import date

import pytest


def test_vencimiento_normalizado():
    from app.services.stock_service import vencimiento_de_ingreso

    hoy = date(2026, 10, 28)
    assert vencimiento_de_ingreso("", hoy) == "28/10/2027"
    assert vencimiento_de_ingreso("1111", hoy) == "28/10/2027"
    assert vencimiento_de_ingreso("1 AÑO", hoy) == "28/10/2027"
    assert vencimiento_de_ingreso("2027-04-09", hoy) == "09/04/2027"
    assert vencimiento_de_ingreso("9/4/27", hoy) == "09/04/2027"
    assert vencimiento_de_ingreso("06/2027", hoy) == "30/06/2027"
    assert vencimiento_de_ingreso("03/28", hoy) == "31/03/2028"
    assert vencimiento_de_ingreso("18/072026", hoy) == "18/07/2026"
    with pytest.raises(ValueError):
        vencimiento_de_ingreso("16/2027", hoy)


def test_lote_o_remito():
    from app.services.stock_service import lote_de_ingreso

    assert lote_de_ingreso("81382", "") == "81382"
    assert lote_de_ingreso("", "0001-00012345") == "Remito 0001-00012345"
    assert lote_de_ingreso("1111", "R-55") == "Remito R-55"
    with pytest.raises(ValueError):
        lote_de_ingreso("S/L", "")


def test_ingreso_sin_lote_ni_vencimiento(app):
    from app.extensions import db
    from app.models import IngresoStock
    from app.services import stock_service
    from app.services import trazabilidad_service as ts

    with app.app_context():
        stock_service.save_ingreso(
            "materia_prima", "Sal Gruesa Lavada", "Prov", "", "", 10, "op", unidad="Bolsas",
            fecha="2026-10-28", hora="09:00", remito="0001-00012345",
        )
        ing = db.session.scalars(db.select(IngresoStock)).one()
        assert (ing.lote, ing.remito, ing.vencimiento) == ("Remito 0001-00012345", "0001-00012345", "28/10/2027")
        assert ts.buscar("0001-00012345")["ingresos"][0].id == ing.id
        with pytest.raises(ValueError):
            stock_service.save_ingreso("materia_prima", "Sal Gruesa Lavada", "Prov", "", "1111", 10, "op", fecha="2026-10-28", hora="09:00")
