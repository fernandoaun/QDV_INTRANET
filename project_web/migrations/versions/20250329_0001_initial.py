"""Esquema inicial vacío (metadata sin tablas hasta modelar el dominio).

Revision ID: 20250329_0001
Revises:
Create Date: 2026-03-29

"""
from typing import Sequence, Union

revision: str = "20250329_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
