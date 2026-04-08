"""producto.stock_minimo_alerta para alertas bajo stock

Revision ID: 20260331_stock_minimo_alerta
Revises: 20260331_producto_requiere_equipo
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260331_stock_minimo_alerta"
down_revision: Union[str, Sequence[str], None] = "20260331_producto_requiere_equipo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    colnames = {c["name"] for c in insp.get_columns("productos_catalogo")}
    if "stock_minimo_alerta" not in colnames:
        op.add_column("productos_catalogo", sa.Column("stock_minimo_alerta", sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    colnames = {c["name"] for c in insp.get_columns("productos_catalogo")}
    if "stock_minimo_alerta" in colnames:
        op.drop_column("productos_catalogo", "stock_minimo_alerta")
