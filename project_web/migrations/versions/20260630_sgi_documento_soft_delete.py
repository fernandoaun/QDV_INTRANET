"""SGI: papelera de documentos (soft delete con recuperación).

Revision ID: 20260630_sgi_documento_soft_delete
Revises: 20260624_sgi_documento_tipo_contenido
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260630_sgi_documento_soft_delete"
down_revision: Union[str, Sequence[str], None] = "20260624_sgi_documento_tipo_contenido"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_documentos" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sgi_documentos")}
    if "codigo_archivado" not in cols:
        op.add_column("sgi_documentos", sa.Column("codigo_archivado", sa.String(length=64), nullable=True))
    if "deleted_at" not in cols:
        op.add_column("sgi_documentos", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_sgi_documentos_deleted_at", "sgi_documentos", ["deleted_at"], unique=False)
    if "deleted_by_id" not in cols:
        op.add_column("sgi_documentos", sa.Column("deleted_by_id", sa.Integer(), nullable=True))
        op.create_index("ix_sgi_documentos_deleted_by_id", "sgi_documentos", ["deleted_by_id"], unique=False)
        op.create_foreign_key(
            "fk_sgi_documentos_deleted_by_id_usuarios",
            "sgi_documentos",
            "usuarios",
            ["deleted_by_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_documentos" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sgi_documentos")}
    if "deleted_by_id" in cols:
        op.drop_constraint("fk_sgi_documentos_deleted_by_id_usuarios", "sgi_documentos", type_="foreignkey")
        op.drop_index("ix_sgi_documentos_deleted_by_id", table_name="sgi_documentos")
        op.drop_column("sgi_documentos", "deleted_by_id")
    if "deleted_at" in cols:
        op.drop_index("ix_sgi_documentos_deleted_at", table_name="sgi_documentos")
        op.drop_column("sgi_documentos", "deleted_at")
    if "codigo_archivado" in cols:
        op.drop_column("sgi_documentos", "codigo_archivado")
