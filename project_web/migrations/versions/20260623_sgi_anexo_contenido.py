"""SGI: tipo de contenido y JSON en anexos (documento visual / organigrama).

Revision ID: 20260623_sgi_anexo_contenido
Revises: 20260620_personal_vacacion_responsable_email
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260623_sgi_anexo_contenido"
down_revision: Union[str, Sequence[str], None] = "20260620_personal_vacacion_responsable_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_procedimiento_anexos" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sgi_procedimiento_anexos")}
    if "tipo_contenido" not in cols:
        op.add_column(
            "sgi_procedimiento_anexos",
            sa.Column("tipo_contenido", sa.String(length=32), nullable=False, server_default="archivo"),
        )
    if "contenido_json" not in cols:
        op.add_column(
            "sgi_procedimiento_anexos",
            sa.Column("contenido_json", sa.Text(), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_procedimiento_anexos" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sgi_procedimiento_anexos")}
    if "contenido_json" in cols:
        op.drop_column("sgi_procedimiento_anexos", "contenido_json")
    if "tipo_contenido" in cols:
        op.drop_column("sgi_procedimiento_anexos", "tipo_contenido")
