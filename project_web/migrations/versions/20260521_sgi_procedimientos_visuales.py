"""SGI: generador visual de procedimientos (PG/PO) — tablas nuevas.

Revision ID: 20260521_sgi_procedimientos_visuales
Revises: 20260520_sgi_module
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260521_sgi_procedimientos_visuales"
down_revision: Union[str, Sequence[str], None] = "20260520_sgi_module"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "sgi_documentos" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sgi_documentos")}
        if "es_procedimiento_visual" not in cols:
            op.add_column(
                "sgi_documentos",
                sa.Column(
                    "es_procedimiento_visual",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
        if "responsable_revision" not in cols:
            op.add_column(
                "sgi_documentos",
                sa.Column(
                    "responsable_revision",
                    sa.String(length=256),
                    nullable=False,
                    server_default=sa.text("''"),
                ),
            )
        if "fecha_aprobacion" not in cols:
            op.add_column("sgi_documentos", sa.Column("fecha_aprobacion", sa.Date(), nullable=True))

    if "sgi_procedimiento_revisiones" in insp.get_table_names():
        return

    op.create_table(
        "sgi_procedimiento_revisiones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("documento_id", sa.Integer(), nullable=False),
        sa.Column("numero_revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision_label", sa.String(length=32), server_default="Rev. 00", nullable=False),
        sa.Column("estado", sa.String(length=32), server_default="borrador", nullable=False),
        sa.Column("contenido_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("fecha_vigencia", sa.Date(), nullable=True),
        sa.Column("elaboro", sa.String(length=256), server_default="", nullable=False),
        sa.Column("reviso", sa.String(length=256), server_default="", nullable=False),
        sa.Column("aprobo", sa.String(length=256), server_default="", nullable=False),
        sa.Column("fecha_elaboracion", sa.Date(), nullable=True),
        sa.Column("fecha_revision", sa.Date(), nullable=True),
        sa.Column("fecha_aprobacion", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["documento_id"], ["sgi_documentos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("documento_id", "numero_revision", name="uq_sgi_proc_rev_doc_num"),
    )
    op.create_index("ix_sgi_proc_rev_documento_id", "sgi_procedimiento_revisiones", ["documento_id"])
    op.create_index("ix_sgi_proc_rev_estado", "sgi_procedimiento_revisiones", ["estado"])

    op.create_table(
        "sgi_procedimiento_control_cambios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision_ref", sa.String(length=32), server_default="", nullable=False),
        sa.Column("descripcion", sa.String(length=4000), server_default="", nullable=False),
        sa.Column("fecha_aprobacion", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["revision_id"], ["sgi_procedimiento_revisiones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sgi_proc_cc_revision_id", "sgi_procedimiento_control_cambios", ["revision_id"])

    op.create_table(
        "sgi_procedimiento_registros",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), server_default="0", nullable=False),
        sa.Column("nombre", sa.String(length=512), server_default="", nullable=False),
        sa.Column("quien_archiva", sa.String(length=512), server_default="", nullable=False),
        sa.Column("como", sa.String(length=512), server_default="", nullable=False),
        sa.Column("donde", sa.String(length=512), server_default="", nullable=False),
        sa.Column("tiempo_guarda", sa.String(length=256), server_default="", nullable=False),
        sa.Column("usuarios", sa.String(length=512), server_default="", nullable=False),
        sa.Column("disposicion_final", sa.String(length=512), server_default="", nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["sgi_procedimiento_revisiones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sgi_proc_reg_revision_id", "sgi_procedimiento_registros", ["revision_id"])

    op.create_table(
        "sgi_procedimiento_anexos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), server_default="0", nullable=False),
        sa.Column("nombre", sa.String(length=512), server_default="", nullable=False),
        sa.Column("codigo", sa.String(length=64), server_default="", nullable=False),
        sa.Column("revision", sa.String(length=32), server_default="", nullable=False),
        sa.Column("fecha_vigencia", sa.Date(), nullable=True),
        sa.Column("archivo_path", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["revision_id"], ["sgi_procedimiento_revisiones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sgi_proc_anx_revision_id", "sgi_procedimiento_anexos", ["revision_id"])

    op.create_table(
        "sgi_procedimiento_aprobaciones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("accion", sa.String(length=64), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("usuario_label", sa.String(length=256), server_default="", nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("detalle", sa.String(length=4000), server_default="", nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["sgi_procedimiento_revisiones.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sgi_proc_apr_revision_id", "sgi_procedimiento_aprobaciones", ["revision_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for tbl in (
        "sgi_procedimiento_aprobaciones",
        "sgi_procedimiento_anexos",
        "sgi_procedimiento_registros",
        "sgi_procedimiento_control_cambios",
        "sgi_procedimiento_revisiones",
    ):
        if tbl in insp.get_table_names():
            op.drop_table(tbl)

    if "sgi_documentos" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sgi_documentos")}
        for col in ("fecha_aprobacion", "responsable_revision", "es_procedimiento_visual"):
            if col in cols:
                op.drop_column("sgi_documentos", col)
