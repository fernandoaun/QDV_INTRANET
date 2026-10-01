"""Parámetros operativos editables (producción estimada de hipoclorito).

Revision ID: 20261001_app_parametros
Revises: 20260930_cargado_por
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261001_app_parametros"
down_revision: str | None = "20260930_cargado_por"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    if "app_parametros" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "app_parametros",
        sa.Column("clave", sa.String(length=64), nullable=False),
        sa.Column("valor", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("clave"),
    )


def downgrade():
    op.drop_table("app_parametros")
