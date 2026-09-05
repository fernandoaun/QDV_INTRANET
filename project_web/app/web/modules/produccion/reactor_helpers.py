"""Serialización y utilidades del circuito reactor (NaOH / concentraciones)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import ReactorRegistro
from app.services.operational_warnings import warnings_for_reactor_registro
from app.services.timer_anchor import (
    effective_anchor_iso,
    last_anchor_iso_for_model,
    last_anchor_iso_for_model_on_date,
)

# Compatibilidad con imports/tests previos.
effective_reactor_anchor_iso = effective_anchor_iso


def next_reactor_lote(fecha_iso: str) -> str:
    n = db.session.scalar(
        select(func.count()).select_from(ReactorRegistro).where(ReactorRegistro.fecha_iso == fecha_iso)
    )
    correlative = int(n or 0) + 1
    dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
    return f"{dt.strftime('%y%m%d')}{correlative:02d}"


def last_reactor_created_at_iso() -> str | None:
    """Último análisis de reactor (cualquier fecha; ancla del vencimiento operativo)."""
    return last_anchor_iso_for_model(ReactorRegistro)


def last_reactor_created_at_iso_for_date(fecha_iso: str) -> str | None:
    return last_anchor_iso_for_model_on_date(ReactorRegistro, fecha_iso)


def _parse_float_text(value: str, label: str) -> float:
    try:
        return float(value.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{label} debe ser numérico.") from exc


def parse_optional_float(text: str | None, label: str) -> float | None:
    value = (text or "").strip()
    if not value:
        return None
    return _parse_float_text(value, label)


def parse_required_float(text: str | None, label: str) -> float:
    value = (text or "").strip()
    if not value:
        raise ValueError(f"{label} es obligatorio.")
    return _parse_float_text(value, label)


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
        "e2_temperatura": r.e2_temperatura,
        "e2_densidad": r.e2_densidad,
        "e2_concentracion": r.e2_concentracion,
        "e3_temperatura": r.e3_temperatura,
        "e3_densidad": r.e3_densidad,
        "e3_concentracion": r.e3_concentracion,
        "observaciones": r.observaciones or "",
        "created_at_iso": r.created_at_iso,
        "warnings": warnings,
    }
