"""Serialización y utilidades del circuito reactor (NaOH / concentraciones)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import ReactorRegistro
from app.services.operational_warnings import warnings_for_reactor_registro


def next_reactor_lote(fecha_iso: str) -> str:
    n = db.session.scalar(
        select(func.count()).select_from(ReactorRegistro).where(ReactorRegistro.fecha_iso == fecha_iso)
    )
    correlative = int(n or 0) + 1
    dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
    return f"{dt.strftime('%y%m%d')}{correlative:02d}"


def last_reactor_created_at_iso_for_date(fecha_iso: str) -> str | None:
    return db.session.scalar(
        select(ReactorRegistro.created_at_iso)
        .where(ReactorRegistro.fecha_iso == fecha_iso)
        .order_by(ReactorRegistro.id.desc())
        .limit(1)
    )


def parse_optional_float(text: str | None, label: str) -> float | None:
    value = (text or "").strip()
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{label} debe ser numérico.") from exc


def reactor_row_to_dict(r: ReactorRegistro) -> dict[str, Any]:
    warnings = warnings_for_reactor_registro(r)
    return {
        "id": r.id,
        "fecha_iso": r.fecha_iso,
        "hora_hm": r.hora_hm,
        "operador": r.operador,
        "lote": r.lote,
        "ph": r.ph,
        "temperatura": r.temperatura,
        "densidad": r.densidad,
        "concentracion_tabla": r.concentracion_tabla,
        "exceso_naoh": r.exceso_naoh,
        "exceso_na2co3": r.exceso_na2co3,
        "orp": r.orp,
        "observaciones": r.observaciones or "",
        "created_at_iso": r.created_at_iso,
        "warnings": warnings,
    }
