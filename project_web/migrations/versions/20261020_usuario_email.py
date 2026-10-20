"""Mail del usuario sin legajo (solo lectura total / SGI): para encontrar su WhatsApp y sus avisos.

Revision ID: 20261020_usuario_email
Revises: 20261020_whatsapp_aviso_adjunto
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261020_usuario_email"
down_revision: str | None = "20261020_whatsapp_aviso_adjunto"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios") as b:
        b.add_column(sa.Column("email", sa.String(256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as b:
        b.drop_column("email")
