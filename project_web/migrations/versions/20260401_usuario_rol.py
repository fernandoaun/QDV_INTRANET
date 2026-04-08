"""usuarios.rol — perfiles administrador / operaciones / logística / mantenimiento / pasante

Revision ID: 20260401_usuario_rol
Revises: 20260331_entregas_module
Create Date: 2026-04-01

- Añade columna rol (default operaciones).
- is_admin=1 → rol administrador; resto operaciones (ajustable luego en admin).
- Valores no reconocidos en el futuro se normalizan en código a operaciones.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260401_usuario_rol"
down_revision: Union[str, Sequence[str], None] = "20260331_entregas_module"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("usuarios", "rol"):
        op.add_column(
            "usuarios",
            sa.Column("rol", sa.String(length=32), nullable=False, server_default="operaciones"),
        )
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE usuarios SET rol = 'administrador' WHERE is_admin = 1"))
    conn.execute(sa.text("UPDATE usuarios SET rol = 'operaciones' WHERE is_admin = 0"))


def downgrade() -> None:
    if _column_exists("usuarios", "rol"):
        op.drop_column("usuarios", "rol")
