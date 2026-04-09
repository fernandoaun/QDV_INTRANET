"""Stock: trazabilidad por lote (FK consumo→ingreso), unidad y datos de ingreso

Revision ID: 20260409_stock_lote_trazabilidad
Revises: 20260408_entregas_catalogos
Create Date: 2026-04-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260409_stock_lote_trazabilidad"
down_revision: Union[str, Sequence[str], None] = "20260408_entregas_catalogos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    is_pg = bind.dialect.name == "postgresql"

    cols_ing = {c["name"] for c in insp.get_columns("ingresos_stock")}
    if "unidad" not in cols_ing:
        op.add_column(
            "ingresos_stock",
            sa.Column("unidad", sa.String(length=64), nullable=False, server_default=""),
        )
    if "observaciones" not in cols_ing:
        op.add_column("ingresos_stock", sa.Column("observaciones", sa.Text(), nullable=True))
    if "proveedor" not in cols_ing:
        op.add_column("ingresos_stock", sa.Column("proveedor", sa.String(length=256), nullable=True))
    if "cargado_por_user_id" not in cols_ing:
        op.add_column("ingresos_stock", sa.Column("cargado_por_user_id", sa.Integer(), nullable=True))
        if is_pg:
            op.create_foreign_key(
                "fk_ingresos_stock_cargado_por_user",
                "ingresos_stock",
                "usuarios",
                ["cargado_por_user_id"],
                ["id"],
            )

    cols_con = {c["name"] for c in insp.get_columns("consumos_stock")}
    if "ingreso_stock_id" not in cols_con:
        op.add_column("consumos_stock", sa.Column("ingreso_stock_id", sa.Integer(), nullable=True))
        op.create_index(
            op.f("ix_consumos_stock_ingreso_stock_id"),
            "consumos_stock",
            ["ingreso_stock_id"],
            unique=False,
        )
        if is_pg:
            op.create_foreign_key(
                "fk_consumos_stock_ingreso_stock",
                "consumos_stock",
                "ingresos_stock",
                ["ingreso_stock_id"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    is_pg = bind.dialect.name == "postgresql"

    cols_con = {c["name"] for c in insp.get_columns("consumos_stock")}
    if "ingreso_stock_id" in cols_con:
        if is_pg:
            op.drop_constraint("fk_consumos_stock_ingreso_stock", "consumos_stock", type_="foreignkey")
        op.drop_index(op.f("ix_consumos_stock_ingreso_stock_id"), table_name="consumos_stock")
        op.drop_column("consumos_stock", "ingreso_stock_id")

    cols_ing = {c["name"] for c in insp.get_columns("ingresos_stock")}
    if "cargado_por_user_id" in cols_ing:
        if is_pg:
            op.drop_constraint("fk_ingresos_stock_cargado_por_user", "ingresos_stock", type_="foreignkey")
        op.drop_column("ingresos_stock", "cargado_por_user_id")
    if "proveedor" in cols_ing:
        op.drop_column("ingresos_stock", "proveedor")
    if "observaciones" in cols_ing:
        op.drop_column("ingresos_stock", "observaciones")
    if "unidad" in cols_ing:
        op.drop_column("ingresos_stock", "unidad")
