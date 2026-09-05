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


def _compose_fecha_hora_iso(fecha_iso: str | None, hora_hm: str | None) -> str | None:
    """Arma un ISO naive `YYYY-MM-DDTHH:MM:SS` a partir de las columnas visibles del registro."""
    f = (fecha_iso or "").strip()
    h = (hora_hm or "").strip()
    if not f or not h:
        return None
    hm = h[:5] if len(h) >= 5 else h
    if len(hm) == 4 and ":" in hm:
        # p.ej. "9:30" → no normalizamos; exige HH:MM
        pass
    if len(hm) < 4:
        return None
    if len(hm) == 5:
        return f"{f}T{hm}:00"
    if len(hm) >= 8:
        return f"{f}T{hm[:8]}"
    return f"{f}T{hm}"


def _parse_anchor_dt(iso: str | None) -> datetime | None:
    s = (iso or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def effective_reactor_anchor_iso(
    fecha_iso: str | None,
    hora_hm: str | None,
    created_at_iso: str | None,
) -> str | None:
    """
    Ancla operativa del cronómetro: el más reciente entre `created_at_iso` y fecha+hora
    del registro (lo que el operador ve en la tabla). Así un created_at viejo/desfasado
    no deja el cronómetro en Atrasado cuando ya hay análisis del día.
    """
    created = (created_at_iso or "").strip() or None
    composed = _compose_fecha_hora_iso(fecha_iso, hora_hm)
    candidates = [c for c in (created, composed) if c]
    if not candidates:
        return None
    best = candidates[0]
    best_dt = _parse_anchor_dt(best)
    for c in candidates[1:]:
        dt = _parse_anchor_dt(c)
        if dt is None:
            continue
        if best_dt is None or dt > best_dt:
            best = c
            best_dt = dt
    return best


def last_reactor_created_at_iso() -> str | None:
    """Último análisis de reactor (cualquier fecha; ancla del vencimiento operativo)."""
    # Candidato por created_at (índice natural) y por fecha+hora visibles en pantalla.
    by_created = db.session.execute(
        select(
            ReactorRegistro.fecha_iso,
            ReactorRegistro.hora_hm,
            ReactorRegistro.created_at_iso,
        )
        .order_by(ReactorRegistro.created_at_iso.desc(), ReactorRegistro.id.desc())
        .limit(1)
    ).first()
    by_fecha_hora = db.session.execute(
        select(
            ReactorRegistro.fecha_iso,
            ReactorRegistro.hora_hm,
            ReactorRegistro.created_at_iso,
        )
        .order_by(
            ReactorRegistro.fecha_iso.desc(),
            ReactorRegistro.hora_hm.desc(),
            ReactorRegistro.id.desc(),
        )
        .limit(1)
    ).first()
    best: str | None = None
    best_dt: datetime | None = None
    for row in (by_created, by_fecha_hora):
        if not row:
            continue
        anchor = effective_reactor_anchor_iso(row.fecha_iso, row.hora_hm, row.created_at_iso)
        dt = _parse_anchor_dt(anchor)
        if anchor and (best_dt is None or (dt is not None and dt > best_dt)):
            best = anchor
            best_dt = dt
    return best


def last_reactor_created_at_iso_for_date(fecha_iso: str) -> str | None:
    row = db.session.execute(
        select(
            ReactorRegistro.fecha_iso,
            ReactorRegistro.hora_hm,
            ReactorRegistro.created_at_iso,
        )
        .where(ReactorRegistro.fecha_iso == fecha_iso)
        .order_by(ReactorRegistro.id.desc())
        .limit(1)
    ).first()
    if not row:
        return None
    return effective_reactor_anchor_iso(row.fecha_iso, row.hora_hm, row.created_at_iso)


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
