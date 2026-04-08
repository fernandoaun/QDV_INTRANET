"""shift_sessions: laboratorista acompañante (FK nullable a usuarios)

Revision ID: 20260405_shift_session_laboratorist
Revises: 20260404_usuario_rol_laboratorista

Usa batch_alter_table para compatibilidad con SQLite (ALTER limitado).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260405_shift_session_laboratorist"
down_revision: Union[str, Sequence[str], None] = "20260404_usuario_rol_laboratorista"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shift_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("laboratorist_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_shift_sessions_laboratorist_user_id_usuarios",
            "usuarios",
            ["laboratorist_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_shift_sessions_laboratorist_user_id", ["laboratorist_user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("shift_sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_shift_sessions_laboratorist_user_id")
        batch_op.drop_constraint("fk_shift_sessions_laboratorist_user_id_usuarios", type_="foreignkey")
        batch_op.drop_column("laboratorist_user_id")
