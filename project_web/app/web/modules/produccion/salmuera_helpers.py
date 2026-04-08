"""Serialización y reglas auxiliares del circuito de salmuera."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

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


def last_salmuera_created_at_iso_for_date(fecha_iso: str) -> str | None:
    return db.session.scalar(
        select(SalmueraRegistro.created_at_iso)
        .where(SalmueraRegistro.fecha_iso == fecha_iso)
        .order_by(SalmueraRegistro.id.desc())
        .limit(1)
    )


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
        "operador": r.operador,
        "lote": r.lote or "",
        "observaciones": r.observaciones or "",
        "atraso_motivo": r.atraso_motivo or "",
        "created_at_iso": r.created_at_iso,
        "warnings": warnings_for_salmuera_registro(r),
    }
