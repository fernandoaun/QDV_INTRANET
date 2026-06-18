"""Aviso por correo en entregas EPP pendientes de confirmación.

Revision ID: 20260618_personal_entrega_epp_aviso_mail
Revises: 20260618_personal_entrega_epp_workflow
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_personal_entrega_epp_aviso_mail"
down_revision: Union[str, Sequence[str], None] = "20260618_personal_entrega_epp_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "personal_entregas_epp",
        sa.Column("aviso_pendiente_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("personal_entregas_epp", "aviso_pendiente_at")
