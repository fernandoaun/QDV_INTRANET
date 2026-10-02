"""Planificación: reglas de tareas repetitivas (series) y fechas únicas dentro de una serie.

Revision ID: 20261003_planif_series
Revises: 20261002_solicitudes_epp
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261003_planif_series"
down_revision: str | None = "20261002_solicitudes_epp"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if "planificacion_series" not in set(insp.get_table_names()):
        op.create_table(
            "planificacion_series",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("regla_json", sa.Text(), nullable=False),
            sa.Column("ancla", sa.Date(), nullable=False),
            sa.Column("duracion_dias", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("generada_hasta", sa.Date(), nullable=True),
            sa.Column("ocurrencias_generadas", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("codigo_base", sa.String(length=48), nullable=True),
            sa.Column("titulo", sa.String(length=256), nullable=False),
            sa.Column("descripcion", sa.Text(), nullable=True),
            sa.Column("responsable_user_id", sa.Integer(), nullable=True),
            sa.Column("categoria", sa.String(length=32), nullable=False, server_default="otro"),
            sa.Column("prioridad", sa.String(length=16), nullable=False, server_default="media"),
            sa.Column("observaciones", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["responsable_user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    idx = {i["name"] for i in insp.get_indexes("planificacion_actividades")}
    if "uq_planif_serie_fecha" not in idx:
        op.create_index("uq_planif_serie_fecha", "planificacion_actividades", ["serie_id", "fecha_inicio"], unique=True)


def downgrade():
    op.drop_index("uq_planif_serie_fecha", table_name="planificacion_actividades")
    op.drop_table("planificacion_series")
