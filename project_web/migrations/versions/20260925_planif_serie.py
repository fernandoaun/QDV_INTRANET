"""Planificación: serie_id para actividades repetitivas.

Revision ID: 20260925_planif_serie
Revises: 20260915_puesto_perm
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20260925_planif_serie"
down_revision: str | None = "20260915_puesto_perm"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("planificacion_actividades")}
    if "serie_id" not in cols:
        op.add_column("planificacion_actividades", sa.Column("serie_id", sa.String(length=32), nullable=True))
        op.create_index("ix_planificacion_actividades_serie_id", "planificacion_actividades", ["serie_id"])


def downgrade():
    op.drop_index("ix_planificacion_actividades_serie_id", table_name="planificacion_actividades")
    op.drop_column("planificacion_actividades", "serie_id")
