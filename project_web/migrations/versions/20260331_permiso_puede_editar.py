"""permisos_usuario.puede_editar para modo solo lectura

Revision ID: 20260331_permiso_puede_editar
Revises: 20260331_stock_minimo_alerta
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260331_permiso_puede_editar"
down_revision: Union[str, Sequence[str], None] = "20260331_stock_minimo_alerta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    colnames = {c["name"] for c in insp.get_columns("permisos_usuario")}
    if "puede_editar" not in colnames:
        op.add_column(
            "permisos_usuario",
            sa.Column("puede_editar", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    colnames = {c["name"] for c in insp.get_columns("permisos_usuario")}
    if "puede_editar" in colnames:
        op.drop_column("permisos_usuario", "puede_editar")
