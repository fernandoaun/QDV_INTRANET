from __future__ import annotations

from app.extensions import db
from app.models import AguaRegistro
from app.web.modules.produccion.agua_helpers import (
    last_agua_created_at_iso,
    last_agua_created_at_iso_for_date,
)


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
