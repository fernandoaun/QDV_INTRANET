"""Solicitud de cambio (QDV-RG-PG-03_01).

Revision ID: 20261026_solicitud_cambio
Revises: 20261020_plan_accion
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261026_solicitud_cambio"
down_revision: str | None = "20261020_plan_accion"
branch_labels: str | None = None
depends_on: str | None = None


def _txt(nombre, largo=None, default=""):
    tipo = sa.String(length=largo) if largo else sa.Text()
    return sa.Column(nombre, tipo, nullable=False, server_default=default)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "solicitudes_cambio" not in tables:
        op.create_table(
            "solicitudes_cambio",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=True),
            _txt("asunto", 255),
            _txt("solicita", 255),
            _txt("estado", 40),
            _txt("sector", 255),
            sa.Column("requerido_para", sa.Date(), nullable=True),
            _txt("razon"),
            _txt("prioridad", 20),
            _txt("descripcion"),
            _txt("tipos"),
            sa.Column("fecha_evaluacion", sa.Date(), nullable=True),
            _txt("equipo_evaluacion"),
            _txt("impactos"),
            _txt("resolucion", 20),
            sa.Column("fecha_resolucion", sa.Date(), nullable=True),
            _txt("acciones_control", default="[]"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_solicitudes_cambio_numero", "solicitudes_cambio", ["numero"])
    if "solicitudes_cambio_cambios" not in tables:
        op.create_table(
            "solicitudes_cambio_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("solicitud_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["solicitud_id"], ["solicitudes_cambio.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_solicitudes_cambio_cambios_solicitud_id", "solicitudes_cambio_cambios", ["solicitud_id"])
        op.create_index("ix_solicitudes_cambio_cambios_created_at", "solicitudes_cambio_cambios", ["created_at"])


def downgrade():
    op.drop_table("solicitudes_cambio_cambios")
    op.drop_table("solicitudes_cambio")
