"""Módulo Vencimientos: sectores, vencimientos e historial.

Revision ID: 20260508_vencimientos_module
Revises: 20260506_deadline_alert_emails
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_vencimientos_module"
down_revision: Union[str, Sequence[str], None] = "20260506_deadline_alert_emails"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sectores_vencimientos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(length=128), nullable=False),
        sa.Column("descripcion", sa.String(length=512), server_default="", nullable=False),
        sa.Column("activo", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sectores_vencimientos_nombre", "sectores_vencimientos", ["nombre"])

    op.create_table(
        "vencimientos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sector_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=256), nullable=False),
        sa.Column("descripcion", sa.String(length=4000), server_default="", nullable=False),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=False),
        sa.Column("responsable", sa.String(length=256), server_default="", nullable=False),
        sa.Column("email_aviso", sa.String(length=256), server_default="", nullable=False),
        sa.Column("estado", sa.String(length=32), server_default="vigente", nullable=False),
        sa.Column("observaciones", sa.String(length=4000), server_default="", nullable=False),
        sa.Column("archivo_path", sa.String(length=512), nullable=True),
        sa.Column("aviso_30_dias_enviado", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("fecha_aviso_30_dias", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("continuacion_de_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["continuacion_de_id"], ["vencimientos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sector_id"], ["sectores_vencimientos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vencimientos_sector_id", "vencimientos", ["sector_id"])
    op.create_index("ix_vencimientos_nombre", "vencimientos", ["nombre"])
    op.create_index("ix_vencimientos_fecha_vencimiento", "vencimientos", ["fecha_vencimiento"])
    op.create_index("ix_vencimientos_continuacion_de_id", "vencimientos", ["continuacion_de_id"])

    op.create_table(
        "vencimientos_historial",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vencimiento_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("usuario", sa.String(length=256), server_default="", nullable=False),
        sa.Column("accion", sa.String(length=64), nullable=False),
        sa.Column("detalle", sa.String(length=8000), server_default="", nullable=False),
        sa.ForeignKeyConstraint(["vencimiento_id"], ["vencimientos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vencimientos_historial_vencimiento_id", "vencimientos_historial", ["vencimiento_id"])
    op.create_index("ix_vencimientos_historial_fecha", "vencimientos_historial", ["fecha"])
    op.create_index("ix_vencimientos_historial_accion", "vencimientos_historial", ["accion"])

    conn = op.get_bind()
    sectors = [
        "Producción",
        "Mantenimiento",
        "Seguridad e Higiene",
        "Administración",
        "Laboratorio",
        "Logística",
        "Medio Ambiente",
        "Habilitaciones",
        "Vehículos",
        "Equipos",
    ]
    ins = sa.text(
        "INSERT INTO sectores_vencimientos (nombre, descripcion, activo) "
        "SELECT :nombre, '', :activo WHERE NOT EXISTS (SELECT 1 FROM sectores_vencimientos WHERE nombre = :nombre)"
    )
    for name in sectors:
        conn.execute(ins, {"nombre": name, "activo": True})


def downgrade() -> None:
    op.drop_index("ix_vencimientos_historial_accion", table_name="vencimientos_historial")
    op.drop_index("ix_vencimientos_historial_fecha", table_name="vencimientos_historial")
    op.drop_index("ix_vencimientos_historial_vencimiento_id", table_name="vencimientos_historial")
    op.drop_table("vencimientos_historial")

    op.drop_index("ix_vencimientos_continuacion_de_id", table_name="vencimientos")
    op.drop_index("ix_vencimientos_fecha_vencimiento", table_name="vencimientos")
    op.drop_index("ix_vencimientos_nombre", table_name="vencimientos")
    op.drop_index("ix_vencimientos_sector_id", table_name="vencimientos")
    op.drop_table("vencimientos")

    op.drop_index("ix_sectores_vencimientos_nombre", table_name="sectores_vencimientos")
    op.drop_table("sectores_vencimientos")
