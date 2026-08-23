"""Módulo Procedimientos y registros (archivo externo / subida de papeles).

Revision ID: 20260823_archivo_module
Revises: 20260724_entregas_carga_multi
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_archivo_module"
down_revision: Union[str, Sequence[str], None] = "20260724_entregas_carga_multi"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "archivo_submodulos" not in tables:
        op.create_table(
            "archivo_submodulos",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("nombre", sa.String(length=256), nullable=False),
            sa.Column("codigo", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("descripcion", sa.String(length=2000), nullable=False, server_default=""),
            sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by_id", sa.Integer(), nullable=True),
            sa.Column("updated_by_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_archivo_submodulos_kind", "archivo_submodulos", ["kind"])
        op.create_index("ix_archivo_submodulos_activo", "archivo_submodulos", ["activo"])

    if "archivo_cargas" not in tables:
        op.create_table(
            "archivo_cargas",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("submodulo_id", sa.Integer(), nullable=False),
            sa.Column("titulo", sa.String(length=256), nullable=False, server_default=""),
            sa.Column("fecha_documento", sa.Date(), nullable=True),
            sa.Column("notas", sa.String(length=2000), nullable=False, server_default=""),
            sa.Column("original_filename", sa.String(length=256), nullable=False),
            sa.Column("stored_path", sa.String(length=1024), nullable=False),
            sa.Column("mime_type", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["submodulo_id"], ["archivo_submodulos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["uploaded_by_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_archivo_cargas_submodulo_id", "archivo_cargas", ["submodulo_id"])
        op.create_index("ix_archivo_cargas_fecha_documento", "archivo_cargas", ["fecha_documento"])
        op.create_index("ix_archivo_cargas_uploaded_at", "archivo_cargas", ["uploaded_at"])
        op.create_index("ix_archivo_cargas_deleted_at", "archivo_cargas", ["deleted_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "archivo_cargas" in tables:
        op.drop_table("archivo_cargas")
    if "archivo_submodulos" in tables:
        op.drop_table("archivo_submodulos")
