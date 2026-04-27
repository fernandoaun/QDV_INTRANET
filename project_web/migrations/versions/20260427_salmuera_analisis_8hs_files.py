"""Salmuera: adjuntos de análisis 8 hs

Revision ID: 20260427_salmuera_analisis_8hs_files
Revises: 20260427_salmuera_analisis_8hs
Create Date: 2026-04-27
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260427_salmuera_analisis_8hs_files"
down_revision: Union[str, Sequence[str], None] = "20260427_salmuera_analisis_8hs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("salmuera_analisis_8hs", sa.Column("file_dureza_path", sa.Text(), nullable=True))
    op.add_column("salmuera_analisis_8hs", sa.Column("file_cloro_libre_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("salmuera_analisis_8hs", "file_cloro_libre_path")
    op.drop_column("salmuera_analisis_8hs", "file_dureza_path")
