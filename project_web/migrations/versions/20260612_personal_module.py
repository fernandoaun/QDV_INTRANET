"""Módulo Personal: legajos, EPP, cursos, vacaciones, ART, apercibimientos.

Revision ID: 20260612_personal_module
Revises: 20260605_sgi_documento_perfiles
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260612_personal_module"
down_revision: Union[str, Sequence[str], None] = "20260605_sgi_documento_perfiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "personal_empleados",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("legajo", sa.String(length=32), nullable=False),
        sa.Column("dni", sa.String(length=16), server_default="", nullable=False),
        sa.Column("cuil", sa.String(length=16), server_default="", nullable=False),
        sa.Column("apellido", sa.String(length=128), nullable=False),
        sa.Column("nombre", sa.String(length=128), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column("domicilio", sa.String(length=256), server_default="", nullable=False),
        sa.Column("telefono", sa.String(length=64), server_default="", nullable=False),
        sa.Column("email", sa.String(length=256), server_default="", nullable=False),
        sa.Column("puesto", sa.String(length=128), server_default="", nullable=False),
        sa.Column("area", sa.String(length=128), server_default="", nullable=False),
        sa.Column("fecha_ingreso", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=16), server_default="activo", nullable=False),
        sa.Column("talle_pantalon", sa.String(length=16), server_default="", nullable=False),
        sa.Column("talle_camisa", sa.String(length=16), server_default="", nullable=False),
        sa.Column("talle_calzado", sa.String(length=16), server_default="", nullable=False),
        sa.Column("talle_guantes", sa.String(length=16), server_default="", nullable=False),
        sa.Column("talle_casco", sa.String(length=16), server_default="", nullable=False),
        sa.Column("observaciones", sa.String(length=4000), server_default="", nullable=False),
        sa.Column("operador_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["operador_id"], ["operadores.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legajo"),
    )
    op.create_index("ix_personal_empleados_apellido", "personal_empleados", ["apellido"])
    op.create_index("ix_personal_empleados_estado", "personal_empleados", ["estado"])
    op.create_index("ix_personal_empleados_fecha_nacimiento", "personal_empleados", ["fecha_nacimiento"])
    op.create_index("ix_personal_empleados_legajo", "personal_empleados", ["legajo"])
    op.create_index("ix_personal_empleados_nombre", "personal_empleados", ["nombre"])
    op.create_index("ix_personal_empleados_operador_id", "personal_empleados", ["operador_id"])

    op.create_table(
        "personal_epp_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(length=128), nullable=False),
        sa.Column("categoria", sa.String(length=32), server_default="epp", nullable=False),
        sa.Column("requiere_talle", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("activo", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("orden", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_index("ix_personal_epp_items_categoria", "personal_epp_items", ["categoria"])
    op.create_index("ix_personal_epp_items_nombre", "personal_epp_items", ["nombre"])

    op.create_table(
        "personal_entregas_epp",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("talle", sa.String(length=32), server_default="", nullable=False),
        sa.Column("cantidad", sa.Integer(), server_default="1", nullable=False),
        sa.Column("observaciones", sa.String(length=2000), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["empleado_id"], ["personal_empleados.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["personal_epp_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personal_entregas_epp_empleado_id", "personal_entregas_epp", ["empleado_id"])
    op.create_index("ix_personal_entregas_epp_fecha", "personal_entregas_epp", ["fecha"])
    op.create_index("ix_personal_entregas_epp_item_id", "personal_entregas_epp", ["item_id"])

    op.create_table(
        "personal_cursos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=256), nullable=False),
        sa.Column("institucion", sa.String(length=256), server_default="", nullable=False),
        sa.Column("fecha_realizacion", sa.Date(), nullable=True),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        sa.Column("observaciones", sa.String(length=2000), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["empleado_id"], ["personal_empleados.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personal_cursos_empleado_id", "personal_cursos", ["empleado_id"])
    op.create_index("ix_personal_cursos_fecha_vencimiento", "personal_cursos", ["fecha_vencimiento"])

    op.create_table(
        "personal_apercibimientos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("tipo", sa.String(length=16), server_default="escrito", nullable=False),
        sa.Column("motivo", sa.String(length=512), server_default="", nullable=False),
        sa.Column("descripcion", sa.String(length=4000), server_default="", nullable=False),
        sa.Column("registrado_por", sa.String(length=256), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["empleado_id"], ["personal_empleados.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personal_apercibimientos_empleado_id", "personal_apercibimientos", ["empleado_id"])
    op.create_index("ix_personal_apercibimientos_fecha", "personal_apercibimientos", ["fecha"])

    op.create_table(
        "personal_art",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("aseguradora", sa.String(length=256), server_default="", nullable=False),
        sa.Column("numero_poliza", sa.String(length=64), server_default="", nullable=False),
        sa.Column("fecha_alta", sa.Date(), nullable=True),
        sa.Column("fecha_baja", sa.Date(), nullable=True),
        sa.Column("observaciones", sa.String(length=2000), server_default="", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["empleado_id"], ["personal_empleados.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empleado_id"),
    )
    op.create_index("ix_personal_art_empleado_id", "personal_art", ["empleado_id"])

    op.create_table(
        "personal_vacaciones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("fecha_desde", sa.Date(), nullable=False),
        sa.Column("fecha_hasta", sa.Date(), nullable=False),
        sa.Column("dias", sa.Integer(), server_default="1", nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=16), server_default="pendiente", nullable=False),
        sa.Column("observaciones", sa.String(length=2000), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["empleado_id"], ["personal_empleados.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personal_vacaciones_anio", "personal_vacaciones", ["anio"])
    op.create_index("ix_personal_vacaciones_empleado_id", "personal_vacaciones", ["empleado_id"])
    op.create_index("ix_personal_vacaciones_estado", "personal_vacaciones", ["estado"])
    op.create_index("ix_personal_vacaciones_fecha_desde", "personal_vacaciones", ["fecha_desde"])
    op.create_index("ix_personal_vacaciones_fecha_hasta", "personal_vacaciones", ["fecha_hasta"])


def downgrade() -> None:
    op.drop_table("personal_vacaciones")
    op.drop_table("personal_art")
    op.drop_table("personal_apercibimientos")
    op.drop_table("personal_cursos")
    op.drop_table("personal_entregas_epp")
    op.drop_table("personal_epp_items")
    op.drop_table("personal_empleados")
