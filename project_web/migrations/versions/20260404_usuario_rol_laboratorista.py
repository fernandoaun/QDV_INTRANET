"""Renombrar perfil pasante → laboratorista (usuarios y sesiones de turno)

Revision ID: 20260404_usuario_rol_laboratorista
Revises: 20260403_shift_warning_record_meta

- usuarios.rol: 'pasante' → 'laboratorista'
- shift_sessions.effective_role: mismo reemplazo por trazabilidad en historial

La reversión no se aplica en downgrade (riesgo de pisar laboratoristas creados después).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260404_usuario_rol_laboratorista"
down_revision: Union[str, Sequence[str], None] = "20260403_shift_warning_record_meta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE usuarios SET rol = 'laboratorista' WHERE lower(trim(rol)) = 'pasante'"))
    op.execute(
        sa.text(
            "UPDATE shift_sessions SET effective_role = 'laboratorista' "
            "WHERE lower(trim(effective_role)) = 'pasante'"
        )
    )


def downgrade() -> None:
    """No revertir automáticamente: mezclaría laboratoristas legítimos con el antiguo pasante."""
