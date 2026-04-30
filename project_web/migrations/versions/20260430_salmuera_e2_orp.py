"""Hipoclorito: ORP en electrolizador 2

Revision ID: 20260430_salmuera_e2_orp
Revises: 20260430_reactor_orp
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260430_salmuera_e2_orp"
down_revision: Union[str, Sequence[str], None] = "20260430_reactor_orp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("salmuera_registros")}
    if "orp" not in cols:
        op.add_column("salmuera_registros", sa.Column("orp", sa.REAL(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("salmuera_registros")}
    if "orp" in cols:
        op.drop_column("salmuera_registros", "orp")
