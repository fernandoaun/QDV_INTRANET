from __future__ import annotations

from app.extensions import db
from app.models import AguaRegistro, ReactorRegistro
from app.web.modules.produccion.agua_helpers import (
    last_agua_created_at_iso,
    last_agua_created_at_iso_for_date,
)
from app.web.modules.produccion.reactor_helpers import last_reactor_created_at_iso


def test_last_agua_created_at_iso_crosses_days(app):
    with app.app_context():
        db.session.add(
            AguaRegistro(
                fecha_iso="2026-08-05",
                hora_hm="22:00",
                turno="N",
                operador="Op",
                lote="26080501",
                numero_columna=1,
                temperatura=25.0,
                dureza=0.5,
                observaciones="",
                created_at_iso="2026-08-05T22:00:00",
            )
        )
        db.session.commit()

        assert last_agua_created_at_iso_for_date("2026-08-06") is None
        assert last_agua_created_at_iso() == "2026-08-05T22:00:00"


def test_last_reactor_uses_latest_created_at_not_max_id(app):
    with app.app_context():
        common = dict(
            fecha_iso="2026-09-03",
            operador="Op",
            ph=7.0,
            temperatura=25.0,
            densidad=1.2,
            concentracion_tabla=300.0,
            exceso_naoh=0.1,
            exceso_na2co3=0.1,
        )
        db.session.add(
            ReactorRegistro(
                **common,
                hora_hm="13:46",
                lote="26090301",
                created_at_iso="2026-09-03T13:46:20",
            )
        )
        db.session.add(
            ReactorRegistro(
                **common,
                hora_hm="13:08",
                lote="26090302",
                created_at_iso="2026-09-03T13:08:00",
            )
        )
        db.session.commit()
        assert last_reactor_created_at_iso() == "2026-09-03T13:46:20"
