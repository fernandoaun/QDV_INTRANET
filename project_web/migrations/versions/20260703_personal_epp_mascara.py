"""Agregar Máscara al catálogo de EPP de Personal.

Revision ID: 20260703_personal_epp_mascara
Revises: 20260630_birthday_reminders_sent
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260703_personal_epp_mascara"
down_revision: Union[str, Sequence[str], None] = "20260630_birthday_reminders_sent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO personal_epp_items (nombre, categoria, requiere_talle, activo, orden) "
            "SELECT :nombre, :categoria, :requiere_talle, :activo, :orden "
            "WHERE NOT EXISTS (SELECT 1 FROM personal_epp_items WHERE lower(nombre) = lower(:nombre))"
        ),
        {
            "nombre": "Máscara",
            "categoria": "epp",
            "requiere_talle": False,
            "activo": True,
            "orden": 95,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM personal_epp_items "
            "WHERE lower(nombre) = lower(:nombre) "
            "AND NOT EXISTS (SELECT 1 FROM personal_entregas_epp WHERE item_id = personal_epp_items.id)"
        ),
        {"nombre": "Máscara"},
    )
