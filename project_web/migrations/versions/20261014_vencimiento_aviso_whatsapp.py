"""Usuarios que reciben por WhatsApp los avisos de vencimientos.

Revision ID: 20261014_vencimiento_aviso_whatsapp
Revises: 20261012_handover_stock_corregido
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261014_vencimiento_aviso_whatsapp"
down_revision: str | None = "20261012_handover_stock_corregido"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    if "vencimiento_aviso_whatsapp" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "vencimiento_aviso_whatsapp",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_vencimiento_aviso_whatsapp_user"),
    )


def downgrade():
    op.drop_table("vencimiento_aviso_whatsapp")
