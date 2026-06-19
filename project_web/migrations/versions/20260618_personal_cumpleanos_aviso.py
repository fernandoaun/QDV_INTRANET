"""Aviso por correo de cumpleaños del día.

Revision ID: 20260618_personal_cumpleanos_aviso
Revises: 20260618_personal_entrega_epp_aviso_mail
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_personal_cumpleanos_aviso"
down_revision: Union[str, Sequence[str], None] = "20260618_personal_entrega_epp_aviso_mail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("personal_empleados")}
    if "aviso_cumpleanos_anio" not in cols:
        op.add_column(
            "personal_empleados",
            sa.Column("aviso_cumpleanos_anio", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("personal_empleados")}
    if "aviso_cumpleanos_anio" in cols:
        op.drop_column("personal_empleados", "aviso_cumpleanos_anio")
