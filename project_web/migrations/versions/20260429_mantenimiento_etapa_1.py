"""Mantenimiento etapa 1: equipos, componentes y correctivos

Revision ID: 20260429_mantenimiento_etapa_1
Revises: 20260427_salmuera_analisis_8hs_files
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260429_mantenimiento_etapa_1"
down_revision: Union[str, Sequence[str], None] = "20260427_salmuera_analisis_8hs_files"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("equipos") as batch_op:
        batch_op.add_column(sa.Column("codigo_interno", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("tipo_equipo", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("area_sector", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("equipo_principal_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("marca", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("modelo", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("numero_serie", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("fecha_alta", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("estado", sa.String(length=32), nullable=False, server_default="operativo"))
        batch_op.add_column(sa.Column("observaciones", sa.Text(), nullable=True))
        batch_op.create_foreign_key("fk_equipos_equipo_principal", "equipos", ["equipo_principal_id"], ["id"])

    op.create_index("ix_equipos_codigo_interno", "equipos", ["codigo_interno"], unique=False)
    op.create_index("ix_equipos_tipo_equipo", "equipos", ["tipo_equipo"], unique=False)
    op.create_index("ix_equipos_area_sector", "equipos", ["area_sector"], unique=False)
    op.create_index("ix_equipos_equipo_principal_id", "equipos", ["equipo_principal_id"], unique=False)
    op.create_index("ix_equipos_estado", "equipos", ["estado"], unique=False)

    op.create_table(
        "maintenance_components",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("equipo_principal_id", sa.Integer(), nullable=False),
        sa.Column("codigo_interno", sa.String(length=64), nullable=True),
        sa.Column("nombre", sa.String(length=256), nullable=False),
        sa.Column("tipo_componente", sa.String(length=128), nullable=True),
        sa.Column("marca", sa.String(length=128), nullable=True),
        sa.Column("modelo", sa.String(length=128), nullable=True),
        sa.Column("numero_serie", sa.String(length=128), nullable=True),
        sa.Column("estado", sa.String(length=32), nullable=False, server_default="operativo"),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["equipo_principal_id"], ["equipos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_components_equipo_principal_id", "maintenance_components", ["equipo_principal_id"], unique=False)
    op.create_index("ix_maintenance_components_codigo_interno", "maintenance_components", ["codigo_interno"], unique=False)
    op.create_index("ix_maintenance_components_tipo_componente", "maintenance_components", ["tipo_componente"], unique=False)
    op.create_index("ix_maintenance_components_estado", "maintenance_components", ["estado"], unique=False)

    op.create_table(
        "maintenance_failures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("detected_at_iso", sa.String(length=32), nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("reported_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reported_by_display", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("descripcion_falla", sa.Text(), nullable=False),
        sa.Column("sintoma_observado", sa.Text(), nullable=True),
        sa.Column("causa_probable", sa.Text(), nullable=True),
        sa.Column("causa_real", sa.Text(), nullable=True),
        sa.Column("criticidad", sa.String(length=16), nullable=False, server_default="media"),
        sa.Column("estado", sa.String(length=32), nullable=False, server_default="reportado"),
        sa.Column("tiempo_fuera_servicio_horas", sa.Float(), nullable=True),
        sa.Column("accion_realizada", sa.Text(), nullable=True),
        sa.Column("repuestos_utilizados", sa.Text(), nullable=True),
        sa.Column("recursos_utilizados", sa.Text(), nullable=True),
        sa.Column("responsable_trabajo", sa.String(length=256), nullable=True),
        sa.Column("closed_at_iso", sa.String(length=32), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["maintenance_components.id"]),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"]),
        sa.ForeignKeyConstraint(["reported_by_user_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_failures_detected_at_iso", "maintenance_failures", ["detected_at_iso"], unique=False)
    op.create_index("ix_maintenance_failures_equipo_id", "maintenance_failures", ["equipo_id"], unique=False)
    op.create_index("ix_maintenance_failures_component_id", "maintenance_failures", ["component_id"], unique=False)
    op.create_index("ix_maintenance_failures_reported_by_user_id", "maintenance_failures", ["reported_by_user_id"], unique=False)
    op.create_index("ix_maintenance_failures_criticidad", "maintenance_failures", ["criticidad"], unique=False)
    op.create_index("ix_maintenance_failures_estado", "maintenance_failures", ["estado"], unique=False)
    op.create_index("ix_maintenance_failures_responsable_trabajo", "maintenance_failures", ["responsable_trabajo"], unique=False)
    op.create_index("ix_maintenance_failures_closed_at_iso", "maintenance_failures", ["closed_at_iso"], unique=False)

    op.create_table(
        "maintenance_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("failure_id", sa.Integer(), nullable=True),
        sa.Column("equipo_id", sa.Integer(), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=256), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["maintenance_components.id"]),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"]),
        sa.ForeignKeyConstraint(["failure_id"], ["maintenance_failures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_attachments_failure_id", "maintenance_attachments", ["failure_id"], unique=False)
    op.create_index("ix_maintenance_attachments_equipo_id", "maintenance_attachments", ["equipo_id"], unique=False)
    op.create_index("ix_maintenance_attachments_component_id", "maintenance_attachments", ["component_id"], unique=False)


def downgrade() -> None:
    op.drop_table("maintenance_attachments")
    op.drop_table("maintenance_failures")
    op.drop_table("maintenance_components")
    with op.batch_alter_table("equipos") as batch_op:
        batch_op.drop_constraint("fk_equipos_equipo_principal", type_="foreignkey")
        batch_op.drop_column("observaciones")
        batch_op.drop_column("estado")
        batch_op.drop_column("fecha_alta")
        batch_op.drop_column("numero_serie")
        batch_op.drop_column("modelo")
        batch_op.drop_column("marca")
        batch_op.drop_column("equipo_principal_id")
        batch_op.drop_column("area_sector")
        batch_op.drop_column("tipo_equipo")
        batch_op.drop_column("codigo_interno")
