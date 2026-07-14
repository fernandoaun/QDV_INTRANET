"""SGI: vincular filas de CONTROL DE REGISTROS a módulos del sistema.

Revision ID: 20260714_sgi_registro_modulo
Revises: 20260703_personal_epp_mascara
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_sgi_registro_modulo"
down_revision: Union[str, Sequence[str], None] = "20260703_personal_epp_mascara"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_procedimiento_registros" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sgi_procedimiento_registros")}
    if "modulo" not in cols:
        op.add_column(
            "sgi_procedimiento_registros",
            sa.Column("modulo", sa.String(length=64), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_procedimiento_registros" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sgi_procedimiento_registros")}
    if "modulo" in cols:
        op.drop_column("sgi_procedimiento_registros", "modulo")
