"""Módulo SGI: documentos e historial.

Revision ID: 20260520_sgi_module
Revises: 20260514_salmuera_voltaje_total_trafo
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260520_sgi_module"
down_revision: Union[str, Sequence[str], None] = "20260514_salmuera_voltaje_total_trafo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_documentos" in insp.get_table_names():
        return

    op.create_table(
        "sgi_documentos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tipo", sa.String(length=8), nullable=False),
        sa.Column("codigo", sa.String(length=64), nullable=False),
        sa.Column("titulo", sa.String(length=512), nullable=False),
        sa.Column("revision", sa.String(length=32), server_default="", nullable=False),
        sa.Column("fecha_creacion_doc", sa.Date(), nullable=True),
        sa.Column("fecha_ultima_revision", sa.Date(), nullable=True),
        sa.Column("responsable_elaboracion", sa.String(length=256), server_default="", nullable=False),
        sa.Column("responsable_aprobacion", sa.String(length=256), server_default="", nullable=False),
        sa.Column("estado", sa.String(length=32), server_default="borrador", nullable=False),
        sa.Column("observaciones", sa.String(length=8000), server_default="", nullable=False),
        sa.Column("archivo_path", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tipo", "codigo", name="uq_sgi_documentos_tipo_codigo"),
    )
    op.create_index("ix_sgi_documentos_tipo", "sgi_documentos", ["tipo"])
    op.create_index("ix_sgi_documentos_codigo", "sgi_documentos", ["codigo"])
    op.create_index("ix_sgi_documentos_titulo", "sgi_documentos", ["titulo"])
    op.create_index("ix_sgi_documentos_estado", "sgi_documentos", ["estado"])
    op.create_index("ix_sgi_documentos_fecha_creacion_doc", "sgi_documentos", ["fecha_creacion_doc"])
    op.create_index("ix_sgi_documentos_fecha_ultima_revision", "sgi_documentos", ["fecha_ultima_revision"])
    op.create_index("ix_sgi_documentos_created_at", "sgi_documentos", ["created_at"])
    op.create_index("ix_sgi_documentos_created_by_id", "sgi_documentos", ["created_by_id"])
    op.create_index("ix_sgi_documentos_updated_by_id", "sgi_documentos", ["updated_by_id"])

    op.create_table(
        "sgi_documentos_historial",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("documento_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("usuario", sa.String(length=256), server_default="", nullable=False),
        sa.Column("accion", sa.String(length=64), nullable=False),
        sa.Column("detalle", sa.String(length=8000), server_default="", nullable=False),
        sa.ForeignKeyConstraint(["documento_id"], ["sgi_documentos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sgi_documentos_historial_documento_id", "sgi_documentos_historial", ["documento_id"])
    op.create_index("ix_sgi_documentos_historial_fecha", "sgi_documentos_historial", ["fecha"])
    op.create_index("ix_sgi_documentos_historial_accion", "sgi_documentos_historial", ["accion"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_documentos_historial" in insp.get_table_names():
        op.drop_index("ix_sgi_documentos_historial_accion", table_name="sgi_documentos_historial")
        op.drop_index("ix_sgi_documentos_historial_fecha", table_name="sgi_documentos_historial")
        op.drop_index("ix_sgi_documentos_historial_documento_id", table_name="sgi_documentos_historial")
        op.drop_table("sgi_documentos_historial")

    if "sgi_documentos" in insp.get_table_names():
        op.drop_index("ix_sgi_documentos_updated_by_id", table_name="sgi_documentos")
        op.drop_index("ix_sgi_documentos_created_by_id", table_name="sgi_documentos")
        op.drop_index("ix_sgi_documentos_created_at", table_name="sgi_documentos")
        op.drop_index("ix_sgi_documentos_fecha_ultima_revision", table_name="sgi_documentos")
        op.drop_index("ix_sgi_documentos_fecha_creacion_doc", table_name="sgi_documentos")
        op.drop_index("ix_sgi_documentos_estado", table_name="sgi_documentos")
        op.drop_index("ix_sgi_documentos_titulo", table_name="sgi_documentos")
        op.drop_index("ix_sgi_documentos_codigo", table_name="sgi_documentos")
        op.drop_index("ix_sgi_documentos_tipo", table_name="sgi_documentos")
        op.drop_table("sgi_documentos")
