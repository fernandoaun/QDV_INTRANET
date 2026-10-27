"""Registro de capacitación (QDV-RG-PG-05_03).

Revision ID: 20261027_capacitacion
Revises: 20261026_matriz_riesgos
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261027_capacitacion"
down_revision: str | None = "20261026_matriz_riesgos"
branch_labels: str | None = None
depends_on: str | None = None


def _txt(nombre, largo=None, default=""):
    tipo = sa.String(length=largo) if largo else sa.Text()
    return sa.Column(nombre, tipo, nullable=False, server_default=default)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "capacitaciones" not in tables:
        op.create_table(
            "capacitaciones",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=True),
            _txt("lugar", 255),
            _txt("duracion", 60),
            _txt("disertantes", 255),
            _txt("tema"),
            _txt("material"),
            _txt("metodos", default="{}"),
            _txt("asistentes", default="[]"),
            _txt("eficaz", 2),
            _txt("nuevas_acciones", 2),
            _txt("nuevas_acciones_detalle"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_capacitaciones_numero", "capacitaciones", ["numero"])
    if "capacitaciones_cambios" not in tables:
        op.create_table(
            "capacitaciones_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("capacitacion_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["capacitacion_id"], ["capacitaciones.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_capacitaciones_cambios_capacitacion_id", "capacitaciones_cambios", ["capacitacion_id"])
        op.create_index("ix_capacitaciones_cambios_created_at", "capacitaciones_cambios", ["created_at"])


def downgrade():
    op.drop_table("capacitaciones_cambios")
    op.drop_table("capacitaciones")
