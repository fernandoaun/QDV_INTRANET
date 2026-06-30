"""Registro en BD de avisos de cumpleaños enviados (una vez por día).

Revision ID: 20260630_birthday_reminders_sent
Revises: 20260630_sgi_documento_soft_delete
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260630_birthday_reminders_sent"
down_revision: Union[str, Sequence[str], None] = "20260630_sgi_documento_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "birthday_reminders_sent",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operacion_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operacion_date",
            "kind",
            "empleado_id",
            name="uq_birthday_reminder_date_kind_empleado",
        ),
    )
    op.create_index(
        "ix_birthday_reminders_sent_operacion_date",
        "birthday_reminders_sent",
        ["operacion_date"],
    )
    op.create_index("ix_birthday_reminders_sent_kind", "birthday_reminders_sent", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_birthday_reminders_sent_kind", table_name="birthday_reminders_sent")
    op.drop_index("ix_birthday_reminders_sent_operacion_date", table_name="birthday_reminders_sent")
    op.drop_table("birthday_reminders_sent")
