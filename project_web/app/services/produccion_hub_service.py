from __future__ import annotations

from app.extensions import db
from app.models import Operador
from app.utils.datetime_operacion import now_operacion_local_iso_seconds


def add_operador(nombre: str) -> str:
    """Persiste un operador de planta. Lanza ValueError si el nombre es vacío."""
    n = (nombre or "").strip()
    if not n:
        raise ValueError("El nombre del operador no puede estar vacío.")
    try:
        db.session.add(Operador(nombre=n, created_at_iso=now_operacion_local_iso_seconds()))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return n
