"""Checklists de inspección por equipo (registros del PO-01, p. ej. QDV-RG-PO-01_07).

Revision ID: 20261106_mant_checklists
Revises: 20261028_ingreso_remito
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261106_mant_checklists"
down_revision: str | None = "20261028_ingreso_remito"
branch_labels: str | None = None
depends_on: str | None = None


def _txt(nombre, largo=None, default=""):
    tipo = sa.String(length=largo) if largo else sa.Text()
    return sa.Column(nombre, tipo, nullable=False, server_default=default)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "mant_checklists" not in tables:
        op.create_table(
            "mant_checklists",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("equipo_id", sa.Integer(), nullable=False),
            _txt("codigo", 64),
            _txt("titulo", 255),
            _txt("items", default="[]"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("equipo_id"),
        )
    if "mant_checklist_registros" not in tables:
        op.create_table(
            "mant_checklist_registros",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("checklist_id", sa.Integer(), nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=False),
            _txt("area", 255),
            _txt("actividad"),
            _txt("respuestas", default="[]"),
            _txt("observaciones"),
            sa.Column("inspector_user_id", sa.Integer(), nullable=True),
            _txt("inspector_nombre", 255),
            sa.Column("inspector_firma_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("planta_user_id", sa.Integer(), nullable=True),
            _txt("planta_nombre", 255),
            sa.Column("planta_firma_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["checklist_id"], ["mant_checklists.id"]),
            sa.ForeignKeyConstraint(["inspector_user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["planta_user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_mant_checklist_registros_checklist_id", "mant_checklist_registros", ["checklist_id"])
        op.create_index("ix_mant_checklist_registros_fecha", "mant_checklist_registros", ["fecha"])


def downgrade():
    op.drop_table("mant_checklist_registros")
    op.drop_table("mant_checklists")
