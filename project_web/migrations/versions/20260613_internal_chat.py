"""Chat interno entre usuarios y perfiles.

Revision ID: 20260613_internal_chat
Revises: 20260612_personal_module
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_internal_chat"
down_revision: Union[str, Sequence[str], None] = "20260612_personal_module"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "internal_chat_threads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="direct", nullable=False),
        sa.Column("title", sa.String(length=256), server_default="", nullable=False),
        sa.Column("target_role", sa.String(length=32), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_internal_chat_threads_created_by_id", "internal_chat_threads", ["created_by_id"], unique=False)

    op.create_table(
        "internal_chat_participants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("last_read_message_id", sa.Integer(), server_default="0", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["internal_chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "user_id", name="uq_chat_participant_thread_user"),
    )
    op.create_index("ix_internal_chat_participants_thread_id", "internal_chat_participants", ["thread_id"], unique=False)
    op.create_index("ix_internal_chat_participants_user_id", "internal_chat_participants", ["user_id"], unique=False)

    op.create_table(
        "internal_chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.String(length=4000), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sender_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thread_id"], ["internal_chat_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_internal_chat_messages_thread_id", "internal_chat_messages", ["thread_id"], unique=False)
    op.create_index("ix_internal_chat_messages_sender_id", "internal_chat_messages", ["sender_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_internal_chat_messages_sender_id", table_name="internal_chat_messages")
    op.drop_index("ix_internal_chat_messages_thread_id", table_name="internal_chat_messages")
    op.drop_table("internal_chat_messages")
    op.drop_index("ix_internal_chat_participants_user_id", table_name="internal_chat_participants")
    op.drop_index("ix_internal_chat_participants_thread_id", table_name="internal_chat_participants")
    op.drop_table("internal_chat_participants")
    op.drop_index("ix_internal_chat_threads_created_by_id", table_name="internal_chat_threads")
    op.drop_table("internal_chat_threads")
