"""Turno operativo: sesiones, entregas y acciones sobre avisos.

Revision ID: 20260402_shift_handover
Revises: 20260401_usuario_rol
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260402_shift_handover"
down_revision: Union[str, Sequence[str], None] = "20260401_usuario_rol"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shift_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("effective_role", sa.String(length=32), nullable=False),
        sa.Column("started_at_iso", sa.String(length=32), nullable=False),
        sa.Column("ended_at_iso", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shift_sessions_user_id", "shift_sessions", ["user_id"], unique=False)
    op.create_index("ix_shift_sessions_status", "shift_sessions", ["status"], unique=False)

    op.create_table(
        "shift_handovers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shift_session_id", sa.Integer(), nullable=False),
        sa.Column("outgoing_user_id", sa.Integer(), nullable=False),
        sa.Column("incoming_user_id", sa.Integer(), nullable=True),
        sa.Column("shift_started_at_iso", sa.String(length=32), nullable=False),
        sa.Column("handed_over_at_iso", sa.String(length=32), nullable=False),
        sa.Column("received_at_iso", sa.String(length=32), nullable=True),
        sa.Column("hypochlorite_stock_liters", sa.Float(), nullable=False),
        sa.Column("closing_notes", sa.Text(), nullable=True),
        sa.Column("reception_status", sa.String(length=64), nullable=True),
        sa.Column("reception_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["incoming_user_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["outgoing_user_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["shift_session_id"], ["shift_sessions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shift_handovers_shift_session_id", "shift_handovers", ["shift_session_id"], unique=False)
    op.create_index("ix_shift_handovers_status", "shift_handovers", ["status"], unique=False)

    op.create_table(
        "shift_handover_warning_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("handover_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_record_id", sa.Integer(), nullable=False),
        sa.Column("warning_code", sa.String(length=128), nullable=False),
        sa.Column("warning_message", sa.Text(), nullable=False),
        sa.Column("action_taken", sa.Text(), nullable=False),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["handover_id"], ["shift_handovers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shift_handover_warning_actions_handover_id",
        "shift_handover_warning_actions",
        ["handover_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_shift_handover_warning_actions_handover_id", table_name="shift_handover_warning_actions")
    op.drop_table("shift_handover_warning_actions")
    op.drop_index("ix_shift_handovers_status", table_name="shift_handovers")
    op.drop_index("ix_shift_handovers_shift_session_id", table_name="shift_handovers")
    op.drop_table("shift_handovers")
    op.drop_index("ix_shift_sessions_status", table_name="shift_sessions")
    op.drop_index("ix_shift_sessions_user_id", table_name="shift_sessions")
    op.drop_table("shift_sessions")
