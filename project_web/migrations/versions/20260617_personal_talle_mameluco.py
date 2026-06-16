"""Renombrar talle_casco a talle_mameluco en legajos de Personal.

Revision ID: 20260617_personal_talle_mameluco
Revises: 20260616_personal_empleado_user
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260617_personal_talle_mameluco"
down_revision: Union[str, Sequence[str], None] = "20260616_personal_empleado_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("personal_empleados", "talle_casco", new_column_name="talle_mameluco")


def downgrade() -> None:
    op.alter_column("personal_empleados", "talle_mameluco", new_column_name="talle_casco")
