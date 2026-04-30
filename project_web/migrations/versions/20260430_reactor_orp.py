"""Circuito de salmuera: ORP puntual

Revision ID: 20260430_reactor_orp
Revises: 20260430_salmuera_orp
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260430_reactor_orp"
down_revision: Union[str, Sequence[str], None] = "20260430_salmuera_orp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    reactor_cols = {c["name"] for c in insp.get_columns("reactor_registros")}
    if "orp" not in reactor_cols:
        op.add_column("reactor_registros", sa.Column("orp", sa.REAL(), nullable=True))

    salmuera_cols = {c["name"] for c in insp.get_columns("salmuera_registros")}
    if "orp" in salmuera_cols:
        op.drop_column("salmuera_registros", "orp")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    salmuera_cols = {c["name"] for c in insp.get_columns("salmuera_registros")}
    if "orp" not in salmuera_cols:
        op.add_column("salmuera_registros", sa.Column("orp", sa.REAL(), nullable=True))

    reactor_cols = {c["name"] for c in insp.get_columns("reactor_registros")}
    if "orp" in reactor_cols:
        op.drop_column("reactor_registros", "orp")
