"""Correos destinatarios de avisos de plazos (panel admin).

Revision ID: 20260506_deadline_alert_emails
Revises: 20260505_deadline_reminders_sent
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260506_deadline_alert_emails"
down_revision: Union[str, Sequence[str], None] = "20260505_deadline_reminders_sent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deadline_alert_emails",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_deadline_alert_emails_email"),
    )


def downgrade() -> None:
    op.drop_table("deadline_alert_emails")
