"""Registra qué usuario hizo cada carga (`cargado_por_user_id`), aparte del operador responsable del turno.

Se engancha al guardado de la sesión de base de datos: cualquier registro nuevo que tenga la columna y no la traiga
completa toma el usuario logueado en la petición web. Así cubre todas las pantallas sin tocar cada formulario.
"""
from __future__ import annotations

from flask import has_request_context, session
from sqlalchemy import event
from sqlalchemy.orm import Session

_registrado = False


def _usuario_de_la_peticion() -> int | None:
    if not has_request_context():
        return None
    uid = session.get("user_id")
    return int(uid) if isinstance(uid, int) or (isinstance(uid, str) and uid.isdigit()) else None


def _completar_cargado_por(sess: Session, flush_context, instances) -> None:
    uid = None
    for obj in sess.new:
        if not hasattr(obj, "cargado_por_user_id") or getattr(obj, "cargado_por_user_id", None) is not None:
            continue
        if uid is None:
            uid = _usuario_de_la_peticion()
            if uid is None:
                return
        obj.cargado_por_user_id = uid


def register() -> None:
    global _registrado
    if not _registrado:
        event.listen(Session, "before_flush", _completar_cargado_por)
        _registrado = True
