"""Cola de avisos por WhatsApp (copia de los mails del sistema).

Revision ID: 20261010_whatsapp_avisos
Revises: 20261006_epp_stock
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261010_whatsapp_avisos"
down_revision: str | None = "20261006_epp_stock"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    if "whatsapp_avisos" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "whatsapp_avisos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telefono_e164", sa.String(length=20), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ultimo_error", sa.String(length=500), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_whatsapp_avisos_creado_en", "whatsapp_avisos", ["creado_en"])
    op.create_index("ix_whatsapp_avisos_enviado_en", "whatsapp_avisos", ["enviado_en"])


def downgrade():
    op.drop_index("ix_whatsapp_avisos_enviado_en", table_name="whatsapp_avisos")
    op.drop_index("ix_whatsapp_avisos_creado_en", table_name="whatsapp_avisos")
    op.drop_table("whatsapp_avisos")
