"""Hora local de planta y línea de operador para formularios de producción/stock."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.auth_utils import current_user
from app.extensions import db
from app.models import Operador
from app.services import shift_handover_service as sh
from app.utils.datetime_operacion import now_operacion_naive_local


def now_local() -> datetime:
    """
    Hora local de referencia para lógica operativa (turno/autocompletados).
    Configurable con APP_TIMEZONE, por defecto America/Argentina/Buenos_Aires.
    """
    return now_operacion_naive_local()


def default_operador_for_salmuera() -> str:
    u = current_user()
    if u and (u.username or "").strip():
        return (u.username or "").strip()
    op = db.session.scalar(select(Operador.nombre).order_by(Operador.nombre).limit(1))
    return str(op or "").strip()


def operador_display_line() -> str:
    u = current_user()
    if u is None:
        return ""
    return sh.operador_turno_display_line(u, sh.get_open_shift_session())


def compute_turno_from_hour(hhmm: str) -> str:
    """
    Turnos (web):
    - N: 00:00 a 07:59
    - M: 08:00 a 15:59
    - T: 16:00 a 23:59
    """
    try:
        h = int((hhmm or "").split(":")[0])
    except Exception:
        h = 0
    if 0 <= h < 8:
        return "N"
    if 8 <= h < 16:
        return "M"
    return "T"
