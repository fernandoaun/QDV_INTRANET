"""Archivo: vincular cargas a procedimientos/registros del SGC.

Revision ID: 20260823_archivo_sgi_link
Revises: 20260823_archivo_module
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_archivo_sgi_link"
down_revision: Union[str, Sequence[str], None] = "20260823_archivo_module"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "archivo_cargas" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("archivo_cargas")}
    if "sgi_documento_id" not in cols:
        op.add_column("archivo_cargas", sa.Column("sgi_documento_id", sa.Integer(), nullable=True))
        op.create_index("ix_archivo_cargas_sgi_documento_id", "archivo_cargas", ["sgi_documento_id"])
        op.create_foreign_key(
            "fk_archivo_cargas_sgi_documento_id",
            "archivo_cargas",
            "sgi_documentos",
            ["sgi_documento_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if "sgi_registro_id" not in cols:
        op.add_column("archivo_cargas", sa.Column("sgi_registro_id", sa.Integer(), nullable=True))
        op.create_index("ix_archivo_cargas_sgi_registro_id", "archivo_cargas", ["sgi_registro_id"])
        op.create_foreign_key(
            "fk_archivo_cargas_sgi_registro_id",
            "archivo_cargas",
            "sgi_procedimiento_registros",
            ["sgi_registro_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "registro_clave" not in cols:
        op.add_column(
            "archivo_cargas",
            sa.Column("registro_clave", sa.String(length=256), nullable=False, server_default=""),
        )
        op.create_index("ix_archivo_cargas_registro_clave", "archivo_cargas", ["registro_clave"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "archivo_cargas" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("archivo_cargas")}
    fks = {fk.get("name") for fk in insp.get_foreign_keys("archivo_cargas")}
    if "fk_archivo_cargas_sgi_registro_id" in fks:
        op.drop_constraint("fk_archivo_cargas_sgi_registro_id", "archivo_cargas", type_="foreignkey")
    if "fk_archivo_cargas_sgi_documento_id" in fks:
        op.drop_constraint("fk_archivo_cargas_sgi_documento_id", "archivo_cargas", type_="foreignkey")
    if "sgi_registro_id" in cols:
        op.drop_index("ix_archivo_cargas_sgi_registro_id", table_name="archivo_cargas")
        op.drop_column("archivo_cargas", "sgi_registro_id")
    if "sgi_documento_id" in cols:
        op.drop_index("ix_archivo_cargas_sgi_documento_id", table_name="archivo_cargas")
        op.drop_column("archivo_cargas", "sgi_documento_id")
    if "registro_clave" in cols:
        op.drop_index("ix_archivo_cargas_registro_clave", table_name="archivo_cargas")
        op.drop_column("archivo_cargas", "registro_clave")
