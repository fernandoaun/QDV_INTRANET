"""SGI: estado revisado, correos de workflow y notificaciones in-app.

Revision ID: 20260604_sgi_workflow_notifications
Revises: 20260529_plant_stop_analisis8_frozen
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260604_sgi_workflow_notifications"
down_revision: Union[str, Sequence[str], None] = "20260529_plant_stop_analisis8_frozen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sgi_procedimiento_revisiones",
        sa.Column("revisor_correo", sa.String(length=256), server_default="", nullable=False),
    )
    op.add_column(
        "sgi_procedimiento_revisiones",
        sa.Column("aprobador_correo", sa.String(length=256), server_default="", nullable=False),
    )
    op.create_table(
        "sgi_notificaciones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("documento_id", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=True),
        sa.Column("mensaje", sa.String(length=512), server_default="", nullable=False),
        sa.Column("enlace", sa.String(length=512), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["documento_id"], ["sgi_documentos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["sgi_procedimiento_revisiones.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sgi_notificaciones_user_id", "sgi_notificaciones", ["user_id"], unique=False)
    op.create_index("ix_sgi_notificaciones_documento_id", "sgi_notificaciones", ["documento_id"], unique=False)
    op.create_index("ix_sgi_notificaciones_created_at", "sgi_notificaciones", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sgi_notificaciones_created_at", table_name="sgi_notificaciones")
    op.drop_index("ix_sgi_notificaciones_documento_id", table_name="sgi_notificaciones")
    op.drop_index("ix_sgi_notificaciones_user_id", table_name="sgi_notificaciones")
    op.drop_table("sgi_notificaciones")
    op.drop_column("sgi_procedimiento_revisiones", "aprobador_correo")
    op.drop_column("sgi_procedimiento_revisiones", "revisor_correo")
