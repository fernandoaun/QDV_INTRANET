"""Perfil mantenimiento_operaciones y asignación a Miguel.

Revision ID: 20260714_rol_mant_ops
Revises: 20260714_sgi_soft_delete_msgi_anexos_iii_iv
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_rol_mant_ops"
down_revision: Union[str, Sequence[str], None] = "20260714_sgi_soft_delete_msgi_anexos_iii_iv"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLE = "mantenimiento_operaciones"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "usuarios" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("usuarios")}
    if "rol" not in cols:
        return
    # Usuario Miguel: mantenimiento (general) con capacidad operativa ocasional.
    bind.execute(
        sa.text(
            """
            UPDATE usuarios
            SET rol = :rol
            WHERE (is_admin IS false OR is_admin IS NULL)
              AND (
                lower(trim(username)) IN ('miguel', 'miguel.aun', 'm.aun')
                OR lower(coalesce(nombre_completo, '')) LIKE '%miguel%'
                OR lower(trim(username)) LIKE 'miguel%'
              )
            """
        ),
        {"rol": _ROLE},
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "usuarios" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("usuarios")}
    if "rol" not in cols:
        return
    bind.execute(
        sa.text(
            """
            UPDATE usuarios
            SET rol = 'mantenimiento'
            WHERE lower(trim(rol)) = :rol
              AND (
                lower(trim(username)) IN ('miguel', 'miguel.aun', 'm.aun')
                OR lower(coalesce(nombre_completo, '')) LIKE '%miguel%'
                OR lower(trim(username)) LIKE 'miguel%'
              )
            """
        ),
        {"rol": _ROLE},
    )
