"""Agua que el chofer lleva en el camión junto con el hipoclorito (no toca stock ni producción).

Revision ID: 20261014_entrega_agua_litros
Revises: 20261014_vencimiento_aviso_whatsapp
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261014_entrega_agua_litros"
down_revision: str | None = "20261014_vencimiento_aviso_whatsapp"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("entregas")}
    if "agua_litros" not in cols:
        op.add_column("entregas", sa.Column("agua_litros", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("entregas", "agua_litros")
