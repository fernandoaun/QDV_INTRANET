"""Tabla deadline_reminders_sent para avisos por mail de plazos.

Revision ID: 20260505_deadline_reminders_sent
Revises: 20260504_security_audit_logs
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_deadline_reminders_sent"
down_revision: Union[str, Sequence[str], None] = "20260504_security_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deadline_reminders_sent",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain", "entity_id", name="uq_deadline_reminder_domain_entity"),
    )
    op.create_index("ix_deadline_reminders_sent_domain", "deadline_reminders_sent", ["domain"])
    op.create_index("ix_deadline_reminders_sent_entity_id", "deadline_reminders_sent", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_deadline_reminders_sent_entity_id", table_name="deadline_reminders_sent")
    op.drop_index("ix_deadline_reminders_sent_domain", table_name="deadline_reminders_sent")
    op.drop_table("deadline_reminders_sent")
