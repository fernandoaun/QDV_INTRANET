"""Workflow entregas EPP/ropa: devolución prenda anterior y confirmación empleado.

Revision ID: 20260618_personal_entrega_epp_workflow
Revises: 20260617_personal_talle_mameluco
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_personal_entrega_epp_workflow"
down_revision: Union[str, Sequence[str], None] = "20260617_personal_talle_mameluco"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "personal_entregas_epp",
        sa.Column("estado", sa.String(length=16), server_default="confirmada", nullable=False),
    )
    op.add_column(
        "personal_entregas_epp",
        sa.Column("prenda_anterior_devuelta", sa.Boolean(), server_default="0", nullable=False),
    )
    op.add_column(
        "personal_entregas_epp",
        sa.Column("prenda_anterior_entrega_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "personal_entregas_epp",
        sa.Column("confirmada_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "personal_entregas_epp",
        sa.Column("confirmada_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_personal_entregas_epp_estado",
        "personal_entregas_epp",
        ["estado"],
    )
    op.create_index(
        "ix_personal_entregas_epp_prenda_anterior_entrega_id",
        "personal_entregas_epp",
        ["prenda_anterior_entrega_id"],
    )
    op.create_foreign_key(
        "fk_personal_entregas_epp_prenda_anterior",
        "personal_entregas_epp",
        "personal_entregas_epp",
        ["prenda_anterior_entrega_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_personal_entregas_epp_confirmada_by",
        "personal_entregas_epp",
        "usuarios",
        ["confirmada_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_personal_entregas_epp_confirmada_by", "personal_entregas_epp", type_="foreignkey")
    op.drop_constraint("fk_personal_entregas_epp_prenda_anterior", "personal_entregas_epp", type_="foreignkey")
    op.drop_index("ix_personal_entregas_epp_prenda_anterior_entrega_id", table_name="personal_entregas_epp")
    op.drop_index("ix_personal_entregas_epp_estado", table_name="personal_entregas_epp")
    op.drop_column("personal_entregas_epp", "confirmada_by_user_id")
    op.drop_column("personal_entregas_epp", "confirmada_at")
    op.drop_column("personal_entregas_epp", "prenda_anterior_entrega_id")
    op.drop_column("personal_entregas_epp", "prenda_anterior_devuelta")
    op.drop_column("personal_entregas_epp", "estado")
