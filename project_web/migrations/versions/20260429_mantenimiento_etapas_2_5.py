"""Mantenimiento etapas 2 a 5

Revision ID: 20260429_mantenimiento_etapas_2_5
Revises: 20260429_mantenimiento_etapa_1
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260429_mantenimiento_etapas_2_5"
down_revision: Union[str, Sequence[str], None] = "20260429_mantenimiento_etapa_1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "maintenance_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("tipo_mantenimiento", sa.String(length=32), nullable=False, server_default="preventivo"),
        sa.Column("nombre", sa.String(length=256), nullable=False),
        sa.Column("frecuencia_dias", sa.Integer(), nullable=True),
        sa.Column("frecuencia_horas_uso", sa.Float(), nullable=True),
        sa.Column("frecuencia_periodo", sa.String(length=32), nullable=True),
        sa.Column("proxima_fecha", sa.String(length=16), nullable=True),
        sa.Column("responsable", sa.String(length=256), nullable=True),
        sa.Column("duracion_estimada_horas", sa.Float(), nullable=True),
        sa.Column("tareas", sa.Text(), nullable=True),
        sa.Column("recursos_necesarios", sa.Text(), nullable=True),
        sa.Column("repuestos_necesarios", sa.Text(), nullable=True),
        sa.Column("herramientas_necesarias", sa.Text(), nullable=True),
        sa.Column("epp_necesarios", sa.Text(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["maintenance_components.id"]),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_plans_equipo_id", "maintenance_plans", ["equipo_id"])
    op.create_index("ix_maintenance_plans_component_id", "maintenance_plans", ["component_id"])
    op.create_index("ix_maintenance_plans_tipo_mantenimiento", "maintenance_plans", ["tipo_mantenimiento"])
    op.create_index("ix_maintenance_plans_proxima_fecha", "maintenance_plans", ["proxima_fecha"])
    op.create_index("ix_maintenance_plans_responsable", "maintenance_plans", ["responsable"])
    op.create_index("ix_maintenance_plans_activo", "maintenance_plans", ["activo"])

    op.create_table(
        "maintenance_predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("tipo_falla", sa.String(length=256), nullable=False),
        sa.Column("cantidad_fallas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("promedio_dias_entre_fallas", sa.Float(), nullable=True),
        sa.Column("ultima_fecha_falla", sa.String(length=16), nullable=True),
        sa.Column("fecha_estimada_proxima", sa.String(length=16), nullable=True),
        sa.Column("nivel_confianza", sa.String(length=16), nullable=False, server_default="bajo"),
        sa.Column("recomendacion", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=32), nullable=False, server_default="sugerida"),
        sa.Column("source_key", sa.String(length=512), nullable=False),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["maintenance_components.id"]),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", name="uq_maintenance_predictions_source_key"),
    )
    op.create_index("ix_maintenance_predictions_equipo_id", "maintenance_predictions", ["equipo_id"])
    op.create_index("ix_maintenance_predictions_component_id", "maintenance_predictions", ["component_id"])
    op.create_index("ix_maintenance_predictions_tipo_falla", "maintenance_predictions", ["tipo_falla"])
    op.create_index("ix_maintenance_predictions_ultima_fecha_falla", "maintenance_predictions", ["ultima_fecha_falla"])
    op.create_index("ix_maintenance_predictions_fecha_estimada_proxima", "maintenance_predictions", ["fecha_estimada_proxima"])
    op.create_index("ix_maintenance_predictions_nivel_confianza", "maintenance_predictions", ["nivel_confianza"])
    op.create_index("ix_maintenance_predictions_estado", "maintenance_predictions", ["estado"])
    op.create_index("ix_maintenance_predictions_source_key", "maintenance_predictions", ["source_key"], unique=True)

    op.create_table(
        "maintenance_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("failure_id", sa.Integer(), nullable=True),
        sa.Column("prediction_id", sa.Integer(), nullable=True),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("tipo_mantenimiento", sa.String(length=32), nullable=False, server_default="preventivo"),
        sa.Column("fecha_programada", sa.String(length=16), nullable=False),
        sa.Column("prioridad", sa.String(length=16), nullable=False, server_default="media"),
        sa.Column("criticidad", sa.String(length=16), nullable=False, server_default="media"),
        sa.Column("responsable", sa.String(length=256), nullable=True),
        sa.Column("estado", sa.String(length=32), nullable=False, server_default="programado"),
        sa.Column("tareas", sa.Text(), nullable=True),
        sa.Column("recursos_necesarios", sa.Text(), nullable=True),
        sa.Column("repuestos_necesarios", sa.Text(), nullable=True),
        sa.Column("herramientas_necesarias", sa.Text(), nullable=True),
        sa.Column("epp_necesarios", sa.Text(), nullable=True),
        sa.Column("tiempo_estimado_horas", sa.Float(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("executed_at_iso", sa.String(length=32), nullable=True),
        sa.Column("closed_at_iso", sa.String(length=32), nullable=True),
        sa.Column("resultado", sa.Text(), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["maintenance_components.id"]),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"]),
        sa.ForeignKeyConstraint(["failure_id"], ["maintenance_failures.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["maintenance_plans.id"]),
        sa.ForeignKeyConstraint(["prediction_id"], ["maintenance_predictions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in (
        "plan_id",
        "failure_id",
        "prediction_id",
        "equipo_id",
        "component_id",
        "tipo_mantenimiento",
        "fecha_programada",
        "prioridad",
        "criticidad",
        "responsable",
        "estado",
        "executed_at_iso",
        "closed_at_iso",
    ):
        op.create_index(f"ix_maintenance_orders_{col}", "maintenance_orders", [col])

    op.create_table(
        "maintenance_resources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("tipo_mantenimiento", sa.String(length=32), nullable=False, server_default="preventivo"),
        sa.Column("categoria", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.String(length=256), nullable=False),
        sa.Column("cantidad", sa.Float(), nullable=True),
        sa.Column("unidad", sa.String(length=64), nullable=True),
        sa.Column("tiempo_estimado_horas", sa.Float(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["maintenance_components.id"]),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_resources_equipo_id", "maintenance_resources", ["equipo_id"])
    op.create_index("ix_maintenance_resources_component_id", "maintenance_resources", ["component_id"])
    op.create_index("ix_maintenance_resources_tipo_mantenimiento", "maintenance_resources", ["tipo_mantenimiento"])
    op.create_index("ix_maintenance_resources_categoria", "maintenance_resources", ["categoria"])
    op.create_index("ix_maintenance_resources_activo", "maintenance_resources", ["activo"])

    op.create_table(
        "maintenance_order_resources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("categoria", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.String(length=256), nullable=False),
        sa.Column("cantidad", sa.Float(), nullable=True),
        sa.Column("unidad", sa.String(length=64), nullable=True),
        sa.Column("tiempo_estimado_horas", sa.Float(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["maintenance_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["maintenance_resources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_order_resources_order_id", "maintenance_order_resources", ["order_id"])
    op.create_index("ix_maintenance_order_resources_categoria", "maintenance_order_resources", ["categoria"])


def downgrade() -> None:
    op.drop_table("maintenance_order_resources")
    op.drop_table("maintenance_resources")
    op.drop_table("maintenance_orders")
    op.drop_table("maintenance_predictions")
    op.drop_table("maintenance_plans")
