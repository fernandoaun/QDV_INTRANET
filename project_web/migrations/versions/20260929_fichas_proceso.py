"""Fichas de proceso (QDV-RG-PG-09_03).

Revision ID: 20260929_fichas_proceso
Revises: 20260929_epp_constancia
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20260929_fichas_proceso"
down_revision: str | None = "20260929_epp_constancia"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "fichas_proceso" not in tables:
        op.create_table(
            "fichas_proceso",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("proceso", sa.String(length=160), nullable=False),
            sa.Column("responsable", sa.String(length=160), nullable=False, server_default=""),
            *[sa.Column(c, sa.Text(), nullable=False, server_default="")
              for c in ("actividades", "entradas", "salidas", "como", "con_que", "con_quien", "indicadores")],
            sa.Column("fecha_actualizacion", sa.Date(), nullable=True),
            sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "fichas_proceso_cambios" not in tables:
        op.create_table(
            "fichas_proceso_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ficha_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["ficha_id"], ["fichas_proceso.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_fichas_proceso_cambios_ficha_id", "fichas_proceso_cambios", ["ficha_id"])
        op.create_index("ix_fichas_proceso_cambios_created_at", "fichas_proceso_cambios", ["created_at"])


def downgrade():
    op.drop_table("fichas_proceso_cambios")
    op.drop_table("fichas_proceso")
