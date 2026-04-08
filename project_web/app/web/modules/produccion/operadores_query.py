"""Consultas ligeras de catálogo para formularios de planta."""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import Operador


def list_operadores_planta() -> list[Operador]:
    return list(db.session.scalars(select(Operador).order_by(Operador.nombre)).all())
