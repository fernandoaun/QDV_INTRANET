"""shift_handover_warning_actions: hora/origen del registro del aviso

Revision ID: 20260403_shift_warning_record_meta
Revises: 20260402_shift_handover
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260403_shift_warning_record_meta"
down_revision: Union[str, Sequence[str], None] = "20260402_shift_handover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("shift_handover_warning_actions", "record_created_at_iso"):
        op.add_column(
            "shift_handover_warning_actions",
            sa.Column("record_created_at_iso", sa.String(length=64), nullable=True),
        )
    if not _column_exists("shift_handover_warning_actions", "origin_display"):
        op.add_column(
            "shift_handover_warning_actions",
            sa.Column("origin_display", sa.String(length=128), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("shift_handover_warning_actions", "origin_display"):
        op.drop_column("shift_handover_warning_actions", "origin_display")
    if _column_exists("shift_handover_warning_actions", "record_created_at_iso"):
        op.drop_column("shift_handover_warning_actions", "record_created_at_iso")
