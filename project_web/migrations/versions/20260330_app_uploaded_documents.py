"""app_uploaded_documents (PDF Hipo Conc y otros)

Revision ID: 20260330_app_docs
Revises: 283ddb2c1925
Create Date: 2026-03-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260330_app_docs"
down_revision: Union[str, Sequence[str], None] = "283ddb2c1925"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_uploaded_documents",
        sa.Column("doc_key", sa.String(length=64), nullable=False),
        sa.Column("stored_filename", sa.String(length=256), nullable=False),
        sa.Column("original_filename", sa.String(length=256), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("doc_key"),
    )


def downgrade() -> None:
    op.drop_table("app_uploaded_documents")
