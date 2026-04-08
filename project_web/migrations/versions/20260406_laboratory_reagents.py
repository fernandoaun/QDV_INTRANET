"""laboratory_reagents y laboratory_reagent_usages

Revision ID: 20260406_lab_reagents
Revises: 20260405_shift_session_laboratorist
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260406_lab_reagents"
down_revision: Union[str, Sequence[str], None] = "20260405_shift_session_laboratorist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "laboratory_reagents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("pdf_stored_filename", sa.String(length=256), nullable=False),
        sa.Column("pdf_original_filename", sa.String(length=256), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_laboratory_reagents_name", "laboratory_reagents", ["name"], unique=False)

    op.create_table(
        "laboratory_reagent_usages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reagent_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("used_at_iso", sa.String(length=32), nullable=False),
        sa.Column("registered_by_user_id", sa.Integer(), nullable=False),
        sa.Column("operator_display_name", sa.String(length=512), nullable=False),
        sa.Column("shift_session_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["reagent_id"], ["laboratory_reagents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["shift_session_id"], ["shift_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_reagent_usages_reagent_id", "laboratory_reagent_usages", ["reagent_id"], unique=False)
    op.create_index("ix_lab_reagent_usages_used_at", "laboratory_reagent_usages", ["used_at_iso"], unique=False)
    op.create_index("ix_lab_reagent_usages_reg_user", "laboratory_reagent_usages", ["registered_by_user_id"], unique=False)
    op.create_index("ix_lab_reagent_usages_shift", "laboratory_reagent_usages", ["shift_session_id"], unique=False)


def downgrade() -> None:
    op.drop_table("laboratory_reagent_usages")
    op.drop_table("laboratory_reagents")
