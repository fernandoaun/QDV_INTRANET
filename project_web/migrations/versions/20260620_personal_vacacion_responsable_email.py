"""Email de contacto del responsable de vacaciones (perfiles sin legajo, ej. Angel).

Revision ID: 20260620_personal_vacacion_responsable_email
Revises: 20260619_personal_vacaciones_workflow
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260620_personal_vacacion_responsable_email"
down_revision: Union[str, Sequence[str], None] = "20260619_personal_vacaciones_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "personal_vacaciones_config",
        sa.Column("responsable_email", sa.String(length=256), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("personal_vacaciones_config", "responsable_email")
