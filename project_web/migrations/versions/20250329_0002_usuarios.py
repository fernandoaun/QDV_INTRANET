"""Tabla usuarios (login web).

Revision ID: 20250329_0002
Revises: 20250329_0001
Create Date: 2026-03-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250329_0002"
down_revision: Union[str, Sequence[str], None] = "20250329_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usuarios_username"), "usuarios", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_usuarios_username"), table_name="usuarios")
    op.drop_table("usuarios")
