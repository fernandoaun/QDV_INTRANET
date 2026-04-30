"""Entregas: cantidades programadas y reales

Revision ID: 20260430_entregas_cantidades_reales
Revises: 20260430_stock_ajustes
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260430_entregas_cantidades_reales"
down_revision: Union[str, Sequence[str], None] = "20260430_stock_ajustes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("entregas")}

    if "cantidad_programada" not in cols:
        op.add_column("entregas", sa.Column("cantidad_programada", sa.Float(), nullable=True))
        op.execute("UPDATE entregas SET cantidad_programada = cantidad WHERE cantidad_programada IS NULL")
    if "cantidad_real_cargada" not in cols:
        op.add_column("entregas", sa.Column("cantidad_real_cargada", sa.Float(), nullable=True))
    if "cantidad_real_entregada" not in cols:
        op.add_column("entregas", sa.Column("cantidad_real_entregada", sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("entregas")}

    if "cantidad_real_entregada" in cols:
        op.drop_column("entregas", "cantidad_real_entregada")
    if "cantidad_real_cargada" in cols:
        op.drop_column("entregas", "cantidad_real_cargada")
    if "cantidad_programada" in cols:
        op.drop_column("entregas", "cantidad_programada")
