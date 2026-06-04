"""SGI: perfiles/sectores aplicables por procedimiento.

Revision ID: 20260605_sgi_documento_perfiles
Revises: 20260604_sgi_workflow_notifications
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260605_sgi_documento_perfiles"
down_revision: Union[str, Sequence[str], None] = "20260604_sgi_workflow_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sgi_documento_perfiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("documento_id", sa.Integer(), nullable=False),
        sa.Column("perfil", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["documento_id"], ["sgi_documentos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("documento_id", "perfil", name="uq_sgi_documento_perfil"),
    )
    op.create_index("ix_sgi_documento_perfiles_documento_id", "sgi_documento_perfiles", ["documento_id"])
    op.create_index("ix_sgi_documento_perfiles_perfil", "sgi_documento_perfiles", ["perfil"])


def downgrade() -> None:
    op.drop_index("ix_sgi_documento_perfiles_perfil", table_name="sgi_documento_perfiles")
    op.drop_index("ix_sgi_documento_perfiles_documento_id", table_name="sgi_documento_perfiles")
    op.drop_table("sgi_documento_perfiles")
