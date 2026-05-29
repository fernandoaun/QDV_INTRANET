"""Paradas de planta: eventos y correo de aviso.

Revision ID: 20260529_plant_stop_events
Revises: 20260528_vencimientos_sector_personal
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_plant_stop_events"
down_revision: Union[str, Sequence[str], None] = "20260528_vencimientos_sector_personal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plant_stop_alert_emails",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_plant_stop_alert_emails_email", "plant_stop_alert_emails", ["email"], unique=True)

    op.create_table(
        "plant_stop_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("circuit_key", sa.String(length=32), nullable=False),
        sa.Column("started_at_iso", sa.String(length=32), nullable=False),
        sa.Column("ended_at_iso", sa.String(length=32), nullable=True),
        sa.Column("operador", sa.String(length=256), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("frozen_remaining_sec", sa.Integer(), nullable=True),
        sa.Column("mail_sent_at_iso", sa.String(length=32), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plant_stop_events_circuit_key", "plant_stop_events", ["circuit_key"], unique=False)
    op.create_index("ix_plant_stop_events_started_at_iso", "plant_stop_events", ["started_at_iso"], unique=False)
    op.create_index("ix_plant_stop_events_ended_at_iso", "plant_stop_events", ["ended_at_iso"], unique=False)
    op.create_index("ix_plant_stop_events_user_id", "plant_stop_events", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_plant_stop_events_user_id", table_name="plant_stop_events")
    op.drop_index("ix_plant_stop_events_ended_at_iso", table_name="plant_stop_events")
    op.drop_index("ix_plant_stop_events_started_at_iso", table_name="plant_stop_events")
    op.drop_index("ix_plant_stop_events_circuit_key", table_name="plant_stop_events")
    op.drop_table("plant_stop_events")
    op.drop_index("ix_plant_stop_alert_emails_email", table_name="plant_stop_alert_emails")
    op.drop_table("plant_stop_alert_emails")
