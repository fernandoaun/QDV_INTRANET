"""Correos y deduplicación para avisos de stock crítico.

Revision ID: 20260616_stock_critical_alert_emails
Revises: 20260613_internal_chat
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260616_stock_critical_alert_emails"
down_revision: Union[str, Sequence[str], None] = "20260613_internal_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_alert_emails",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_stock_alert_emails_email"),
    )
    op.create_index("ix_stock_alert_emails_email", "stock_alert_emails", ["email"], unique=True)

    op.create_table(
        "stock_critical_alerts_sent",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("categoria", sa.String(length=64), nullable=False),
        sa.Column("producto", sa.String(length=256), nullable=False),
        sa.Column("sent_at_iso", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("categoria", "producto", name="uq_stock_critical_alert_cat_prod"),
    )


def downgrade() -> None:
    op.drop_table("stock_critical_alerts_sent")
    op.drop_index("ix_stock_alert_emails_email", table_name="stock_alert_emails")
    op.drop_table("stock_alert_emails")
