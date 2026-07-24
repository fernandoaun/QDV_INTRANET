"""Entregas: una carga de camión puede asignarse a varias entregas

Revision ID: 20260724_entregas_carga_multi
Revises: 20260721_sgi_record_definitions
Create Date: 2026-07-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_entregas_carga_multi"
down_revision: Union[str, Sequence[str], None] = "20260721_sgi_record_definitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("entregas")}

    if "carga_grupo_id" not in cols:
        op.add_column("entregas", sa.Column("carga_grupo_id", sa.String(length=36), nullable=True))
        op.create_index("ix_entregas_carga_grupo_id", "entregas", ["carga_grupo_id"], unique=False)
    if "carga_origen_entrega_id" not in cols:
        op.add_column("entregas", sa.Column("carga_origen_entrega_id", sa.Integer(), nullable=True))
        op.create_index(
            "ix_entregas_carga_origen_entrega_id", "entregas", ["carga_origen_entrega_id"], unique=False
        )
        op.create_foreign_key(
            "fk_entregas_carga_origen_entrega_id",
            "entregas",
            "entregas",
            ["carga_origen_entrega_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("entregas")}
    fks = {fk["name"] for fk in insp.get_foreign_keys("entregas")}
    idxs = {ix["name"] for ix in insp.get_indexes("entregas")}

    if "fk_entregas_carga_origen_entrega_id" in fks:
        op.drop_constraint("fk_entregas_carga_origen_entrega_id", "entregas", type_="foreignkey")
    if "ix_entregas_carga_origen_entrega_id" in idxs:
        op.drop_index("ix_entregas_carga_origen_entrega_id", table_name="entregas")
    if "carga_origen_entrega_id" in cols:
        op.drop_column("entregas", "carga_origen_entrega_id")
    if "ix_entregas_carga_grupo_id" in idxs:
        op.drop_index("ix_entregas_carga_grupo_id", table_name="entregas")
    if "carga_grupo_id" in cols:
        op.drop_column("entregas", "carga_grupo_id")
