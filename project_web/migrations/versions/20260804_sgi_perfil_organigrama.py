"""Widen sgi_documento_perfiles.perfil for organigrama puesto ids.

Revision ID: 20260804_sgi_perfil_organigrama
Revises: 20260724_entregas_carga_multi
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_sgi_perfil_organigrama"
down_revision: Union[str, Sequence[str], None] = "20260724_entregas_carga_multi"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sgi_documento_perfiles") as batch:
        batch.alter_column(
            "perfil",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("sgi_documento_perfiles") as batch:
        batch.alter_column(
            "perfil",
            existing_type=sa.String(length=64),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
