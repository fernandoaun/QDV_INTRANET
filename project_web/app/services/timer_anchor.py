"""Ancla operativa compartida de cronómetros de producción.

Usa el máximo entre `created_at_iso` y fecha+hora visibles en la planilla, para que
un created_at desfasado no deje el cronómetro en Atrasado cuando ya hay registro del día.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import InstrumentedAttribute


def compose_fecha_hora_iso(fecha_iso: str | None, hora_hm: str | None) -> str | None:
    """Arma un ISO naive `YYYY-MM-DDTHH:MM:SS` a partir de las columnas visibles."""
    f = (fecha_iso or "").strip()
    h = (hora_hm or "").strip()
    if not f or not h:
        return None
    hm = h[:5] if len(h) >= 5 else h
    if len(hm) < 4:
        return None
    if len(hm) == 5:
        return f"{f}T{hm}:00"
    if len(hm) >= 8:
        return f"{f}T{hm[:8]}"
    return f"{f}T{hm}"


def parse_anchor_dt(iso: str | None) -> datetime | None:
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


def effective_anchor_iso(
    fecha_iso: str | None,
    hora_hm: str | None,
    created_at_iso: str | None,
) -> str | None:
    """El más reciente entre created_at y fecha+hora del registro."""
    created = (created_at_iso or "").strip() or None
    composed = compose_fecha_hora_iso(fecha_iso, hora_hm)
    candidates = [c for c in (created, composed) if c]
    if not candidates:
        return None
    best = candidates[0]
    best_dt = parse_anchor_dt(best)
    for c in candidates[1:]:
        dt = parse_anchor_dt(c)
        if dt is None:
            continue
        if best_dt is None or dt > best_dt:
            best = c
            best_dt = dt
    return best


def _pick_best_anchor(rows: list[Any]) -> str | None:
    best: str | None = None
    best_dt: datetime | None = None
    for row in rows:
        if not row:
            continue
        anchor = effective_anchor_iso(row.fecha_iso, row.hora_hm, row.created_at_iso)
        dt = parse_anchor_dt(anchor)
        if anchor and (best_dt is None or (dt is not None and dt > best_dt)):
            best = anchor
            best_dt = dt
    return best


def last_anchor_iso_for_model(
    model: Any,
    *,
    extra_where: list[Any] | None = None,
) -> str | None:
    """
    Ancla global: mejor entre el último por created_at y el último por fecha+hora.
    `model` debe tener fecha_iso, hora_hm, created_at_iso, id.
    """
    fecha_col: InstrumentedAttribute = model.fecha_iso
    hora_col: InstrumentedAttribute = model.hora_hm
    created_col: InstrumentedAttribute = model.created_at_iso
    id_col: InstrumentedAttribute = model.id

    def _base() -> Select[Any]:
        stmt = select(fecha_col, hora_col, created_col)
        if extra_where:
            for clause in extra_where:
                stmt = stmt.where(clause)
        return stmt

    from app.extensions import db

    by_created = db.session.execute(
        _base().order_by(created_col.desc(), id_col.desc()).limit(1)
    ).first()
    by_fecha_hora = db.session.execute(
        _base().order_by(fecha_col.desc(), hora_col.desc(), id_col.desc()).limit(1)
    ).first()
    return _pick_best_anchor([by_created, by_fecha_hora])


def last_anchor_iso_for_model_on_date(
    model: Any,
    fecha_iso: str,
    *,
    extra_where: list[Any] | None = None,
) -> str | None:
    from app.extensions import db

    clauses = [model.fecha_iso == fecha_iso]
    if extra_where:
        clauses.extend(extra_where)
    row = db.session.execute(
        select(model.fecha_iso, model.hora_hm, model.created_at_iso)
        .where(*clauses)
        .order_by(model.id.desc())
        .limit(1)
    ).first()
    if not row:
        return None
    return effective_anchor_iso(row.fecha_iso, row.hora_hm, row.created_at_iso)
