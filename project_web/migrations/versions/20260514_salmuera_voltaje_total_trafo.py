"""Hipoclorito: voltaje total lectura trafo

Revision ID: 20260514_salmuera_voltaje_total_trafo
Revises: 20260508_vencimientos_module
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260514_salmuera_voltaje_total_trafo"
down_revision: Union[str, Sequence[str], None] = "20260508_vencimientos_module"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("salmuera_registros")}
    if "voltaje_total_trafo" not in cols:
        op.add_column(
            "salmuera_registros",
            sa.Column("voltaje_total_trafo", sa.REAL(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("salmuera_registros")}
    if "voltaje_total_trafo" in cols:
        op.drop_column("salmuera_registros", "voltaje_total_trafo")
