"""Workflow vacaciones: períodos, responsable y estados de solicitud.

Revision ID: 20260619_personal_vacaciones_workflow
Revises: 20260618_personal_entrega_epp_aviso_mail
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260619_personal_vacaciones_workflow"
down_revision: Union[str, Sequence[str], None] = "20260618_personal_entrega_epp_aviso_mail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "personal_vacaciones_periodos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("dias_asignados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("observaciones", sa.String(length=2000), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["empleado_id"], ["personal_empleados.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empleado_id", "anio", name="uq_personal_vac_periodo_empleado_anio"),
    )
    op.create_index("ix_personal_vacaciones_periodos_anio", "personal_vacaciones_periodos", ["anio"])
    op.create_index("ix_personal_vacaciones_periodos_empleado_id", "personal_vacaciones_periodos", ["empleado_id"])

    op.create_table(
        "personal_vacaciones_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("responsable_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["responsable_user_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_personal_vacaciones_config_responsable_user_id",
        "personal_vacaciones_config",
        ["responsable_user_id"],
    )

    op.add_column("personal_vacaciones", sa.Column("periodo_id", sa.Integer(), nullable=True))
    op.add_column(
        "personal_vacaciones",
        sa.Column("motivo_responsable", sa.String(length=2000), server_default="", nullable=False),
    )
    op.add_column("personal_vacaciones", sa.Column("fecha_desde_original", sa.Date(), nullable=True))
    op.add_column("personal_vacaciones", sa.Column("fecha_hasta_original", sa.Date(), nullable=True))
    op.add_column("personal_vacaciones", sa.Column("solicitada_by_user_id", sa.Integer(), nullable=True))
    op.add_column("personal_vacaciones", sa.Column("gestionada_by_user_id", sa.Integer(), nullable=True))
    op.add_column("personal_vacaciones", sa.Column("gestionada_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("personal_vacaciones", sa.Column("confirmada_empleado_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("personal_vacaciones", sa.Column("solicitud_aviso_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_personal_vacaciones_periodo_id", "personal_vacaciones", ["periodo_id"])
    op.create_foreign_key(
        "fk_personal_vacaciones_periodo",
        "personal_vacaciones",
        "personal_vacaciones_periodos",
        ["periodo_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_personal_vacaciones_solicitada_by",
        "personal_vacaciones",
        "usuarios",
        ["solicitada_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_personal_vacaciones_gestionada_by",
        "personal_vacaciones",
        "usuarios",
        ["gestionada_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        sa.text(
            "UPDATE personal_vacaciones SET estado = 'aprobada' "
            "WHERE estado = 'pendiente' AND solicitada_by_user_id IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE personal_vacaciones SET estado = 'solicitada' "
            "WHERE estado = 'pendiente' AND solicitada_by_user_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE personal_vacaciones SET estado = 'pendiente' "
            "WHERE estado IN ('solicitada', 'aprobada', 'modificada', 'rechazada')"
        )
    )
    op.drop_constraint("fk_personal_vacaciones_gestionada_by", "personal_vacaciones", type_="foreignkey")
    op.drop_constraint("fk_personal_vacaciones_solicitada_by", "personal_vacaciones", type_="foreignkey")
    op.drop_constraint("fk_personal_vacaciones_periodo", "personal_vacaciones", type_="foreignkey")
    op.drop_index("ix_personal_vacaciones_periodo_id", table_name="personal_vacaciones")
    op.drop_column("personal_vacaciones", "solicitud_aviso_at")
    op.drop_column("personal_vacaciones", "confirmada_empleado_at")
    op.drop_column("personal_vacaciones", "gestionada_at")
    op.drop_column("personal_vacaciones", "gestionada_by_user_id")
    op.drop_column("personal_vacaciones", "solicitada_by_user_id")
    op.drop_column("personal_vacaciones", "fecha_hasta_original")
    op.drop_column("personal_vacaciones", "fecha_desde_original")
    op.drop_column("personal_vacaciones", "motivo_responsable")
    op.drop_column("personal_vacaciones", "periodo_id")
    op.drop_index("ix_personal_vacaciones_config_responsable_user_id", table_name="personal_vacaciones_config")
    op.drop_table("personal_vacaciones_config")
    op.drop_index("ix_personal_vacaciones_periodos_empleado_id", table_name="personal_vacaciones_periodos")
    op.drop_index("ix_personal_vacaciones_periodos_anio", table_name="personal_vacaciones_periodos")
    op.drop_table("personal_vacaciones_periodos")
