"""SGI: tipo de contenido en documentos MSGI independientes (QDV-ANEXO I–IV).

Revision ID: 20260624_sgi_documento_tipo_contenido
Revises: 20260623_sgi_anexo_contenido
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_sgi_documento_tipo_contenido"
down_revision: Union[str, Sequence[str], None] = "20260623_sgi_anexo_contenido"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_documentos" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sgi_documentos")}
    if "tipo_contenido" not in cols:
        op.add_column(
            "sgi_documentos",
            sa.Column("tipo_contenido", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_documentos" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sgi_documentos")}
    if "tipo_contenido" in cols:
        op.drop_column("sgi_documentos", "tipo_contenido")
