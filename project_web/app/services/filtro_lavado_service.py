"""Servicio de registro de lavado y enjuague de filtro (circuito salmuera, 24 h)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import FiltroLavadoRegistro


def last_filtro_created_at_iso() -> str | None:
    """Último created_at_iso global (para cronómetro). Misma regla que electrolizadores/reactor."""
    return db.session.scalar(
        select(FiltroLavadoRegistro.created_at_iso)
        .order_by(FiltroLavadoRegistro.created_at_iso.desc(), FiltroLavadoRegistro.id.desc())
        .limit(1)
    )


def last_filtro_created_at_iso_for_date(fecha_iso: str) -> str | None:
    return db.session.scalar(
        select(FiltroLavadoRegistro.created_at_iso)
        .where(FiltroLavadoRegistro.fecha_iso == fecha_iso)
        .order_by(FiltroLavadoRegistro.created_at_iso.desc(), FiltroLavadoRegistro.id.desc())
        .limit(1)
    )


def filtro_rows_for_date(fecha_iso: str) -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(FiltroLavadoRegistro)
        .where(FiltroLavadoRegistro.fecha_iso == fecha_iso)
        .order_by(FiltroLavadoRegistro.created_at_iso.desc(), FiltroLavadoRegistro.id.desc())
    ).all()
    return [filtro_row_to_dict(r) for r in rows]


def filtro_row_to_dict(r: FiltroLavadoRegistro) -> dict[str, Any]:
    return {
        "id": r.id,
        "fecha_iso": r.fecha_iso,
        "hora_hm": r.hora_hm,
        "operador": r.operador,
        "observaciones": r.observaciones or "",
        "created_at_iso": r.created_at_iso,
    }
