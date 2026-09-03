"""Add filtro_lavado_registros table.

Revision ID: 20260903_filtro
Revises: 20260827_reactor_entrada_electrolizadores
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_filtro"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "filtro_lavado_registros",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fecha_iso", sa.String(16), nullable=False, index=True),
        sa.Column("hora_hm", sa.String(8), nullable=False),
        sa.Column("operador", sa.String(256), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("created_at_iso", sa.String(32), nullable=False),
    )


def downgrade():
    op.drop_table("filtro_lavado_registros")
