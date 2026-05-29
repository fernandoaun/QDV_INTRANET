"""Paradas de planta: congelar también cronómetro análisis 8 hs (circuito salmuera).

Revision ID: 20260529_plant_stop_analisis8_frozen
Revises: 20260529_plant_stop_events
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_plant_stop_analisis8_frozen"
down_revision: Union[str, Sequence[str], None] = "20260529_plant_stop_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plant_stop_events",
        sa.Column("frozen_remaining_sec_analisis8", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plant_stop_events", "frozen_remaining_sec_analisis8")
