"""Lote de producción: uno por turno (P + aammdd + correlativo de turnos iniciados ese día).

Los análisis de agua, reactor y salmuera llevan el lote del turno en curso a la hora del
análisis. Entre la entrega y la recepción de un turno sigue valiendo el lote del que entregó.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.extensions import db
from app.models import ShiftSession
from app.services import shift_handover_service as sh


def siguiente_lote_produccion(started_at_iso: str) -> str:
    prefijo = f"P{started_at_iso[2:4]}{started_at_iso[5:7]}{started_at_iso[8:10]}"
    usados = db.session.scalars(
        select(ShiftSession.lote_produccion).where(ShiftSession.lote_produccion.like(f"{prefijo}%"))
    ).all()
    n = max((int(x[len(prefijo):]) for x in usados if x and x[len(prefijo):].isdigit()), default=0)
    return f"{prefijo}{n + 1:02d}"


def turno_en(momento_iso: str) -> ShiftSession | None:
    """Último turno iniciado hasta ese momento (incluye el hueco entre entrega y recepción)."""
    return db.session.scalars(
        select(ShiftSession)
        .where(ShiftSession.started_at_iso <= momento_iso, ShiftSession.lote_produccion.isnot(None))
        .order_by(ShiftSession.started_at_iso.desc(), ShiftSession.id.desc())
        .limit(1)
    ).first()


def lote_produccion_en(fecha_iso: str, hora_hm: str) -> str:
    """Lote para un análisis; sin turno registrado devuelve P<aammdd>00."""
    turno = turno_en(f"{fecha_iso}T{hora_hm}:59")
    if turno is not None:
        return str(turno.lote_produccion)
    return f"P{datetime.strptime(fecha_iso, '%Y-%m-%d').strftime('%y%m%d')}00"


def turno_de_lote(lote: str) -> ShiftSession | None:
    return db.session.scalars(select(ShiftSession).where(ShiftSession.lote_produccion == (lote or "").strip().upper())).first()


def inicio_turno_siguiente(turno: ShiftSession) -> str | None:
    """Hasta cuándo vale el lote; None si es el turno en curso."""
    return db.session.scalar(
        select(ShiftSession.started_at_iso)
        .where(ShiftSession.started_at_iso > turno.started_at_iso)
        .order_by(ShiftSession.started_at_iso)
        .limit(1)
    )


def marcar_observado(turno: ShiftSession, nota: str, user_id: int | None) -> None:
    nota = (nota or "").strip()
    if not nota:
        raise ValueError("Escribí el motivo de la observación.")
    turno.lote_observado_nota = nota
    turno.lote_observado_at_iso = sh.now_local_iso()
    turno.lote_observado_por_user_id = user_id


def quitar_observacion(turno: ShiftSession) -> None:
    turno.lote_observado_nota = None
    turno.lote_observado_at_iso = None
    turno.lote_observado_por_user_id = None
