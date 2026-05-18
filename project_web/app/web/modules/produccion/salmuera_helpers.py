"""Serialización y reglas auxiliares del circuito de salmuera."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.constants import SALMUERA_PANEL_ELECTROLIZADORES
from app.extensions import db
from app.models import SalmueraRegistro
from app.services.operational_warnings import warnings_for_salmuera_registro


def parse_voltajes(text: str, n: int) -> list[float]:
    parts = [p.strip() for p in (text or "").replace(";", ",").split(",") if p.strip()]
    if len(parts) != n:
        raise ValueError(f"Tenés que ingresar exactamente {n} voltajes (separados por coma).")
    return [float(p.replace(",", ".")) for p in parts]


def next_salmuera_lote(fecha_iso: str) -> str:
    n = db.session.scalar(
        select(func.count()).select_from(SalmueraRegistro).where(SalmueraRegistro.fecha_iso == fecha_iso)
    )
    correlative = int(n or 0) + 1
    dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
    return f"{dt.strftime('%y%m%d')}{correlative:02d}"


def distinct_salmuera_electrolizador_ids() -> list[int]:
    """Electrolizadores que aparecen en la tabla de salmuera (hipoclorito), ordenados."""
    rows = db.session.scalars(
        select(SalmueraRegistro.electrolizador)
        .where(SalmueraRegistro.electrolizador > 0)
        .distinct()
        .order_by(SalmueraRegistro.electrolizador.asc())
    ).all()
    return [int(x) for x in rows]


def last_salmuera_created_at_iso_for_electrolizador_and_date(fecha_iso: str, electrolizador: int) -> str | None:
    """Último análisis del electrolizador en la fecha de planilla (mismo criterio temporal que el cronómetro por día)."""
    return db.session.scalar(
        select(SalmueraRegistro.created_at_iso)
        .where(
            SalmueraRegistro.fecha_iso == fecha_iso,
            SalmueraRegistro.electrolizador == int(electrolizador),
        )
        .order_by(SalmueraRegistro.id.desc())
        .limit(1)
    )


def salmuera_timer_rows_for_date(fecha_iso: str) -> list[dict[str, Any]]:
    """Filas para cronómetros por electrolizador: último registro de ese equipo en `fecha_iso`.

    Una fila por cada electrolizador configurado en `SALMUERA_PANEL_ELECTROLIZADORES`
    (independientemente de si ya hay historial), para mantener la UI dual estable.
    """
    return [
        {
            "electrolizador": int(eid),
            "last_created_at_iso": last_salmuera_created_at_iso_for_electrolizador_and_date(fecha_iso, int(eid)),
        }
        for eid in SALMUERA_PANEL_ELECTROLIZADORES
    ]


def last_salmuera_row_dict_for_electrolizador_on_date(fecha_iso: str, electrolizador: int) -> dict[str, Any] | None:
    """Último registro del día para un electrolizador (para resumen en panel)."""
    row = db.session.scalar(
        select(SalmueraRegistro)
        .where(
            SalmueraRegistro.fecha_iso == fecha_iso,
            SalmueraRegistro.electrolizador == int(electrolizador),
        )
        .order_by(SalmueraRegistro.created_at_iso.desc(), SalmueraRegistro.id.desc())
        .limit(1)
    )
    return salmuera_row_to_dict(row) if row else None


def count_consecutive_single_cell_for_electrolizador(
    electrolizador: int, *, exclude_id: int | None = None
) -> int:
    q = (
        select(SalmueraRegistro.id, SalmueraRegistro.cantidad_celdas)
        .where(SalmueraRegistro.electrolizador == int(electrolizador))
        .order_by(SalmueraRegistro.id.desc())
        .limit(30)
    )
    rows = list(db.session.execute(q).all())
    count = 0
    for rid, celdas in rows:
        if exclude_id is not None and int(rid) == int(exclude_id):
            continue
        if int(celdas or 0) == 1:
            count += 1
            continue
        break
    return count


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


def salmuera_row_to_dict(r: SalmueraRegistro) -> dict[str, Any]:
    try:
        vj = json.loads(r.voltajes_json) if r.voltajes_json else []
    except json.JSONDecodeError:
        vj = []
    return {
        "id": r.id,
        "fecha_iso": r.fecha_iso,
        "hora_hm": r.hora_hm,
        "electrolizador": r.electrolizador,
        "cantidad_celdas": r.cantidad_celdas,
        "turno": r.turno,
        "voltajes_celdas": vj,
        "voltaje_total": r.voltaje_total,
        "voltaje_total_trafo": r.voltaje_total_trafo,
        "amperaje": r.amperaje,
        "caudal_agua_l_h": r.caudal_agua_l_h,
        "caudal_salmuera_l_h": r.caudal_salmuera_l_h,
        "hipo_conc": r.hipo_conc,
        "hipo_exceso_soda": r.hipo_exceso_soda,
        "sal_temp": r.sal_temp,
        "sal_conc": r.sal_conc,
        "sal_ph": r.sal_ph,
        "soda_conc": r.soda_conc,
        "declor_ph": r.declor_ph,
        "orp": r.orp,
        "operador": r.operador,
        "lote": r.lote or "",
        "observaciones": r.observaciones or "",
        "atraso_motivo": r.atraso_motivo or "",
        "created_at_iso": r.created_at_iso,
        "warnings": warnings_for_salmuera_registro(r),
    }
