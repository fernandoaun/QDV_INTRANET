"""Stock de ropa/EPP: movimientos (ingresos, entregas, ajustes), stock por talle y mínimo por ítem.

Revision ID: 20261006_epp_stock
Revises: 20261003_planif_series
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261006_epp_stock"
down_revision: str | None = "20261003_planif_series"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("personal_epp_items")}
    if "stock_por_talle" not in cols:
        op.add_column("personal_epp_items", sa.Column("stock_por_talle", sa.Boolean(), nullable=False, server_default=sa.false()))
        # Ropa y calzado (categoría «ropa») y guantes se cuentan por talle; el resto, solo el total.
        op.execute(
            "UPDATE personal_epp_items SET stock_por_talle = TRUE "
            "WHERE categoria = 'ropa' OR lower(nombre) LIKE 'guante%'"
        )
    if "stock_minimo" not in cols:
        op.add_column("personal_epp_items", sa.Column("stock_minimo", sa.Integer(), nullable=True))
    if "personal_epp_movimientos" not in set(insp.get_table_names()):
        op.create_table(
            "personal_epp_movimientos",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("talle", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("tipo", sa.String(length=16), nullable=False),
            sa.Column("cantidad", sa.Integer(), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=False),
            sa.Column("proveedor", sa.String(length=256), nullable=False, server_default=""),
            sa.Column("marca", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("observaciones", sa.String(length=1000), nullable=False, server_default=""),
            sa.Column("entrega_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["personal_epp_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["entrega_id"], ["personal_entregas_epp.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        for c in ("item_id", "tipo", "fecha", "entrega_id", "created_at"):
            op.create_index(f"ix_personal_epp_movimientos_{c}", "personal_epp_movimientos", [c])


def downgrade():
    op.drop_table("personal_epp_movimientos")
    op.drop_column("personal_epp_items", "stock_minimo")
    op.drop_column("personal_epp_items", "stock_por_talle")
