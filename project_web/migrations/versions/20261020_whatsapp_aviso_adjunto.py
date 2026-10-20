"""Adjunto (PDF) en los avisos por WhatsApp.

Revision ID: 20261020_whatsapp_aviso_adjunto
Revises: 20261019_perfiles_puesto
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261020_whatsapp_aviso_adjunto"
down_revision: str | None = "20261019_perfiles_puesto"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("whatsapp_avisos") as b:
        b.add_column(sa.Column("adjunto_path", sa.String(255), nullable=False, server_default=""))
        b.add_column(sa.Column("adjunto_nombre", sa.String(160), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("whatsapp_avisos") as b:
        b.drop_column("adjunto_nombre")
        b.drop_column("adjunto_path")
