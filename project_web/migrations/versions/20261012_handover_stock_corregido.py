"""Entrega de turno: stock de hipoclorito tal como lo informó el saliente, si el entrante lo corrigió.

Revision ID: 20261012_handover_stock_corregido
Revises: 20261010_whatsapp_avisos
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261012_handover_stock_corregido"
down_revision: str | None = "20261010_whatsapp_avisos"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("shift_handovers")}
    if "hypochlorite_stock_liters_informado" in cols:
        return
    with op.batch_alter_table("shift_handovers") as batch:
        batch.add_column(sa.Column("hypochlorite_stock_liters_informado", sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table("shift_handovers") as batch:
        batch.drop_column("hypochlorite_stock_liters_informado")
