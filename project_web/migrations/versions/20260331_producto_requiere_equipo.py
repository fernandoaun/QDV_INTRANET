"""producto.requiere_equipo para consumo con equipo obligatorio

Revision ID: 20260331_producto_requiere_equipo
Revises: 20260330_app_docs
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260331_producto_requiere_equipo"
down_revision: Union[str, Sequence[str], None] = "20260330_app_docs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    colnames = {c["name"] for c in insp.get_columns("productos_catalogo")}
    if "requiere_equipo" not in colnames:
        op.add_column(
            "productos_catalogo",
            sa.Column("requiere_equipo", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.execute(
        "UPDATE productos_catalogo SET requiere_equipo = 1 "
        "WHERE lower(trim(tipo_producto)) = 'filtro'"
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    colnames = {c["name"] for c in insp.get_columns("productos_catalogo")}
    if "requiere_equipo" in colnames:
        op.drop_column("productos_catalogo", "requiere_equipo")
