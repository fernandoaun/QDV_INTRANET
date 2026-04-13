"""Planificación: dependencias entre actividades (FS/SS/FF/SF)

Revision ID: 20260414_planificacion_dependencias
Revises: 20260413_planificacion_actividades
Create Date: 2026-04-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260414_planificacion_dependencias"
down_revision: Union[str, Sequence[str], None] = "20260413_planificacion_actividades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planificacion_dependencias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("predecesora_id", sa.Integer(), nullable=False),
        sa.Column("sucesora_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=4), nullable=False, server_default="FS"),
        sa.Column("lag_dias", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["predecesora_id"], ["planificacion_actividades.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sucesora_id"], ["planificacion_actividades.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("predecesora_id", "sucesora_id", name="uq_planificacion_dep_pred_suc"),
    )
    op.create_index("ix_planificacion_dep_sucesora", "planificacion_dependencias", ["sucesora_id"], unique=False)
    op.create_index("ix_planificacion_dep_predecesora", "planificacion_dependencias", ["predecesora_id"], unique=False)


def downgrade() -> None:
    op.drop_table("planificacion_dependencias")
