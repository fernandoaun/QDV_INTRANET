"""Pedidos de EPP hechos por el personal desde la plataforma.

Revision ID: 20261002_solicitudes_epp
Revises: 20261001_app_parametros
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261002_solicitudes_epp"
down_revision: str | None = "20261001_app_parametros"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    if "personal_solicitudes_epp" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "personal_solicitudes_epp",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("talle", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("cantidad", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("motivo", sa.String(length=32), nullable=False),
        sa.Column("comentario", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("estado", sa.String(length=16), nullable=False, server_default="pendiente"),
        sa.Column("respuesta", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("entrega_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resuelta_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resuelta_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["empleado_id"], ["personal_empleados.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["personal_epp_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entrega_id"], ["personal_entregas_epp.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resuelta_by_user_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personal_solicitudes_epp_empleado_id", "personal_solicitudes_epp", ["empleado_id"])
    op.create_index("ix_personal_solicitudes_epp_estado", "personal_solicitudes_epp", ["estado"])
    op.create_index("ix_personal_solicitudes_epp_created_at", "personal_solicitudes_epp", ["created_at"])


def downgrade():
    op.drop_table("personal_solicitudes_epp")
