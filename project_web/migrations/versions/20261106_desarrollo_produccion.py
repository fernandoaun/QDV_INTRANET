"""Diseño y desarrollo de producción (QDV-PO-03: registros 03_01 a 03_04).

Revision ID: 20261106_desarrollo_produccion
Revises: 20261106_mant_checklists
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261106_desarrollo_produccion"
down_revision: str | None = "20261106_mant_checklists"
branch_labels: str | None = None
depends_on: str | None = None


def _txt(nombre, largo=None, default=""):
    tipo = sa.String(length=largo) if largo else sa.Text()
    return sa.Column(nombre, tipo, nullable=False, server_default=default)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "desarrollos_produccion" not in tables:
        op.create_table(
            "desarrollos_produccion",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("fecha_inicio", sa.Date(), nullable=False),
            _txt("producto_proceso", 255),
            _txt("tipo", 32),
            _txt("motivo"),
            sa.Column("prueba_desde", sa.Date(), nullable=False),
            sa.Column("prueba_hasta", sa.Date(), nullable=True),
            _txt("datos", default="{}"),
            _txt("firmas", default="{}"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_desarrollos_produccion_numero", "desarrollos_produccion", ["numero"])
    if "desarrollos_cambios" not in tables:
        op.create_table(
            "desarrollos_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("desarrollo_id", sa.Integer(), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=False),
            _txt("datos", default="{}"),
            _txt("firmas", default="{}"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["desarrollo_id"], ["desarrollos_produccion.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_desarrollos_cambios_numero", "desarrollos_cambios", ["numero"])
        op.create_index("ix_desarrollos_cambios_desarrollo_id", "desarrollos_cambios", ["desarrollo_id"])
    if "desarrollos_historial" not in tables:
        op.create_table(
            "desarrollos_historial",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("desarrollo_id", sa.Integer(), nullable=False),
            sa.Column("cambio_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            _txt("detalle"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["desarrollo_id"], ["desarrollos_produccion.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["cambio_id"], ["desarrollos_cambios.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_desarrollos_historial_desarrollo_id", "desarrollos_historial", ["desarrollo_id"])
        op.create_index("ix_desarrollos_historial_created_at", "desarrollos_historial", ["created_at"])


def downgrade():
    op.drop_table("desarrollos_historial")
    op.drop_table("desarrollos_cambios")
    op.drop_table("desarrollos_produccion")
