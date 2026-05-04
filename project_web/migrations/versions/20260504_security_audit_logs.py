"""Tabla security_audit_logs para auditoría de seguridad y operación.

Revision ID: 20260504_security_audit_logs
Revises: 20260430_entregas_cantidades_reales
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260504_security_audit_logs"
down_revision: Union[str, Sequence[str], None] = "20260430_entregas_cantidades_reales"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "security_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_username", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_audit_logs_occurred_at", "security_audit_logs", ["occurred_at"])
    op.create_index("ix_security_audit_logs_actor_user_id", "security_audit_logs", ["actor_user_id"])
    op.create_index("ix_security_audit_logs_action", "security_audit_logs", ["action"])
    op.create_index("ix_security_audit_logs_module", "security_audit_logs", ["module"])


def downgrade() -> None:
    op.drop_index("ix_security_audit_logs_module", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_action", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_actor_user_id", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_occurred_at", table_name="security_audit_logs")
    op.drop_table("security_audit_logs")
