"""Agregar sector Personal en vencimientos.

Revision ID: 20260528_vencimientos_sector_personal
Revises: 20260521_sgi_procedimientos_visuales
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_vencimientos_sector_personal"
down_revision: Union[str, Sequence[str], None] = "20260521_sgi_procedimientos_visuales"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO sectores_vencimientos (nombre, descripcion, activo) "
            "SELECT :nombre, '', :activo "
            "WHERE NOT EXISTS (SELECT 1 FROM sectores_vencimientos WHERE lower(nombre) = lower(:nombre))"
        ),
        {"nombre": "Personal", "activo": True},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM sectores_vencimientos "
            "WHERE lower(nombre) = lower(:nombre) "
            "AND NOT EXISTS (SELECT 1 FROM vencimientos WHERE sector_id = sectores_vencimientos.id)"
        ),
        {"nombre": "Personal"},
    )
