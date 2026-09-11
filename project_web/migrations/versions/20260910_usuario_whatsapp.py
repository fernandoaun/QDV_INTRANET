"""Add usuarios.whatsapp_e164 for WhatsApp identity.

Revision ID: 20260910_whatsapp
Revises: 20260903_filtro
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20260910_whatsapp"
down_revision: str | None = "20260903_filtro"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    op.add_column("usuarios", sa.Column("whatsapp_e164", sa.String(length=20), nullable=True))
    op.create_index("ix_usuarios_whatsapp_e164", "usuarios", ["whatsapp_e164"], unique=True)


def downgrade():
    op.drop_index("ix_usuarios_whatsapp_e164", table_name="usuarios")
    op.drop_column("usuarios", "whatsapp_e164")
