"""Programa de Objetivos (QDV-RG-PG-02_01).

Revision ID: 20260929_objetivos
Revises: 20260925_planif_serie
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20260929_objetivos"
down_revision: str | None = "20260925_planif_serie"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "objetivos_programas" not in tables:
        op.create_table(
            "objetivos_programas",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("anio", sa.Integer(), nullable=False),
            sa.Column("codigo", sa.String(length=64), nullable=False, server_default="QDV-RG-PG-02_01"),
            sa.Column("revision", sa.String(length=16), nullable=False, server_default="00"),
            sa.Column("fecha_vigencia", sa.Date(), nullable=True),
            sa.Column("fecha_actualizacion", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("anio"),
        )
        op.create_index("ix_objetivos_programas_anio", "objetivos_programas", ["anio"])
    if "objetivos" not in tables:
        op.create_table(
            "objetivos",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("programa_id", sa.Integer(), nullable=False),
            sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("proceso", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("objetivo", sa.Text(), nullable=False, server_default=""),
            sa.Column("meta", sa.String(length=256), nullable=False, server_default=""),
            sa.Column("indicador", sa.String(length=256), nullable=False, server_default=""),
            sa.Column("estado_cumplimiento", sa.String(length=24), nullable=True),
            sa.Column("recursos", sa.Text(), nullable=False, server_default=""),
            sa.Column("frecuencia", sa.String(length=64), nullable=False, server_default="Mensual"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["programa_id"], ["objetivos_programas.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_objetivos_programa_id", "objetivos", ["programa_id"])
    if "objetivos_meses" not in tables:
        op.create_table(
            "objetivos_meses",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("objetivo_id", sa.Integer(), nullable=False),
            sa.Column("mes", sa.Integer(), nullable=False),
            sa.Column("estado", sa.String(length=24), nullable=True),
            sa.Column("valor", sa.String(length=64), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["objetivo_id"], ["objetivos.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("objetivo_id", "mes", name="uq_objetivos_meses_obj_mes"),
        )
        op.create_index("ix_objetivos_meses_objetivo_id", "objetivos_meses", ["objetivo_id"])
    if "objetivos_cambios" not in tables:
        op.create_table(
            "objetivos_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("programa_id", sa.Integer(), nullable=False),
            sa.Column("objetivo_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=64), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["programa_id"], ["objetivos_programas.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["objetivo_id"], ["objetivos.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_objetivos_cambios_programa_id", "objetivos_cambios", ["programa_id"])
        op.create_index("ix_objetivos_cambios_objetivo_id", "objetivos_cambios", ["objetivo_id"])
        op.create_index("ix_objetivos_cambios_created_at", "objetivos_cambios", ["created_at"])


def downgrade():
    op.drop_table("objetivos_cambios")
    op.drop_table("objetivos_meses")
    op.drop_table("objetivos")
    op.drop_table("objetivos_programas")
