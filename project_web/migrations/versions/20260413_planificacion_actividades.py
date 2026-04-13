"""Tabla planificacion_actividades (módulo Planificación / Gantt)

Revision ID: 20260413_planificacion_actividades
Revises: 20260409_stock_lote_trazabilidad
Create Date: 2026-04-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260413_planificacion_actividades"
down_revision: Union[str, Sequence[str], None] = "20260409_stock_lote_trazabilidad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planificacion_actividades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("codigo", sa.String(length=64), nullable=True),
        sa.Column("titulo", sa.String(length=256), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=False),
        sa.Column("duracion_dias", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("responsable_user_id", sa.Integer(), nullable=True),
        sa.Column("categoria", sa.String(length=32), nullable=False, server_default="otro"),
        sa.Column("prioridad", sa.String(length=16), nullable=False, server_default="media"),
        sa.Column("estado", sa.String(length=24), nullable=False, server_default="pendiente"),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("linked_entity_type", sa.String(length=32), nullable=True),
        sa.Column("linked_entity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["responsable_user_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo", name="uq_planificacion_actividades_codigo"),
    )
    op.create_index("ix_planificacion_actividades_fecha_inicio", "planificacion_actividades", ["fecha_inicio"], unique=False)
    op.create_index("ix_planificacion_actividades_fecha_fin", "planificacion_actividades", ["fecha_fin"], unique=False)
    op.create_index("ix_planificacion_actividades_responsable", "planificacion_actividades", ["responsable_user_id"], unique=False)
    op.create_index("ix_planificacion_actividades_categoria", "planificacion_actividades", ["categoria"], unique=False)
    op.create_index("ix_planificacion_actividades_prioridad", "planificacion_actividades", ["prioridad"], unique=False)
    op.create_index("ix_planificacion_actividades_estado", "planificacion_actividades", ["estado"], unique=False)
    op.create_index("ix_planificacion_actividades_linked_type", "planificacion_actividades", ["linked_entity_type"], unique=False)
    op.create_index("ix_planificacion_actividades_linked_id", "planificacion_actividades", ["linked_entity_id"], unique=False)


def downgrade() -> None:
    op.drop_table("planificacion_actividades")
