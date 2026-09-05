from __future__ import annotations

from app.extensions import db
from app.models import FiltroLavadoRegistro
from app.services.filtro_lavado_service import last_filtro_created_at_iso


def test_last_filtro_uses_latest_created_at_not_max_id(app):
    """Misma regla que electrolizadores/reactor: ancla = max(created_at_iso), no max(id)."""
    with app.app_context():
        db.session.add(
            FiltroLavadoRegistro(
                fecha_iso="2026-09-03",
                hora_hm="13:46",
                operador="Op",
                observaciones="",
                created_at_iso="2026-09-03T13:46:20",
            )
        )
        db.session.add(
            FiltroLavadoRegistro(
                fecha_iso="2026-09-03",
                hora_hm="13:08",
                operador="Op",
                observaciones="",
                created_at_iso="2026-09-03T13:08:00",
            )
        )
        db.session.commit()
        assert last_filtro_created_at_iso() == "2026-09-03T13:46:20"
