"""producto.is_stockable para consumos sin descuento de stock

Revision ID: 20260407_producto_is_stockable
Revises: 20260406_lab_reagents
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260407_producto_is_stockable"
down_revision: Union[str, Sequence[str], None] = "20260406_lab_reagents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    colnames = {c["name"] for c in insp.get_columns("productos_catalogo")}
    if "is_stockable" not in colnames:
        op.add_column(
            "productos_catalogo",
            sa.Column("is_stockable", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    colnames = {c["name"] for c in insp.get_columns("productos_catalogo")}
    if "is_stockable" in colnames:
        op.drop_column("productos_catalogo", "is_stockable")
