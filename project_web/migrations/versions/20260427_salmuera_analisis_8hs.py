"""Salmuera: análisis 8 hs de dureza y cloro libre

Revision ID: 20260427_salmuera_analisis_8hs
Revises: 20260414_planificacion_dependencias
Create Date: 2026-04-27
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260427_salmuera_analisis_8hs"
down_revision: Union[str, Sequence[str], None] = "20260414_planificacion_dependencias"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "salmuera_analisis_8hs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fecha", sa.String(length=16), nullable=False),
        sa.Column("hora", sa.String(length=8), nullable=False),
        sa.Column("fecha_hora_iso", sa.String(length=32), nullable=False),
        sa.Column("turno", sa.String(length=64), nullable=False),
        sa.Column("operador", sa.String(length=256), nullable=False),
        sa.Column("dureza_salmuera", sa.Float(), nullable=False),
        sa.Column("cloro_libre_salmuera", sa.Float(), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_salmuera_analisis_8hs_fecha", "salmuera_analisis_8hs", ["fecha"], unique=False)
    op.create_index(
        "ix_salmuera_analisis_8hs_fecha_hora_iso",
        "salmuera_analisis_8hs",
        ["fecha_hora_iso"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("salmuera_analisis_8hs")
