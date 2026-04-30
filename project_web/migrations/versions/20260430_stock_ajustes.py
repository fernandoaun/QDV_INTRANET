"""Stock: ajustes administrativos

Revision ID: 20260430_stock_ajustes
Revises: 20260430_salmuera_e2_orp
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260430_stock_ajustes"
down_revision: Union[str, Sequence[str], None] = "20260430_salmuera_e2_orp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_ajustes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("categoria", sa.String(length=32), nullable=False),
        sa.Column("producto", sa.String(length=256), nullable=False),
        sa.Column("marca", sa.String(length=256), nullable=False),
        sa.Column("cantidad", sa.Float(), nullable=False),
        sa.Column("fecha", sa.String(length=16), nullable=False),
        sa.Column("hora", sa.String(length=8), nullable=False),
        sa.Column("operador", sa.String(length=256), nullable=False),
        sa.Column("motivo", sa.String(length=256), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("ingreso_stock_id", sa.Integer(), nullable=True),
        sa.Column("admin_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["ingreso_stock_id"], ["ingresos_stock.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_ajustes_categoria", "stock_ajustes", ["categoria"])
    op.create_index("ix_stock_ajustes_producto", "stock_ajustes", ["producto"])
    op.create_index("ix_stock_ajustes_fecha", "stock_ajustes", ["fecha"])
    op.create_index("ix_stock_ajustes_ingreso_stock_id", "stock_ajustes", ["ingreso_stock_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_ajustes_ingreso_stock_id", table_name="stock_ajustes")
    op.drop_index("ix_stock_ajustes_fecha", table_name="stock_ajustes")
    op.drop_index("ix_stock_ajustes_producto", table_name="stock_ajustes")
    op.drop_index("ix_stock_ajustes_categoria", table_name="stock_ajustes")
    op.drop_table("stock_ajustes")
