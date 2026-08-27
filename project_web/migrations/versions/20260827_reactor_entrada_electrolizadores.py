"""Reactor: entrada electrolizadores 2 y 3

Revision ID: 20260827_reactor_entrada_el
Revises: 20260823_archivo_sgi_link
Create Date: 2026-08-27
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260827_reactor_entrada_el"
down_revision: Union[str, Sequence[str], None] = "20260823_archivo_sgi_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = (
    "e2_temperatura",
    "e2_densidad",
    "e2_concentracion",
    "e3_temperatura",
    "e3_densidad",
    "e3_concentracion",
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns("reactor_registros")}
    for name in _COLS:
        if name not in existing:
            op.add_column("reactor_registros", sa.Column(name, sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns("reactor_registros")}
    for name in reversed(_COLS):
        if name in existing:
            op.drop_column("reactor_registros", name)
