"""Add filtro_lavado_registros table.

Revision ID: 20260903_filtro
Revises: 20260827_reactor_entrada_electrolizadores
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20260903_filtro"
# Importante: mantener la cadena lineal de migraciones para evitar "multiple heads".
down_revision: str | None = "20260827_reactor_entrada_el"
branch_labels: str | None = None
depends_on: str | None = None


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
