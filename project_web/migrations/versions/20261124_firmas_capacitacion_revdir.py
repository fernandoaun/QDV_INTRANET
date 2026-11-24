"""Firma del disertante en el registro de capacitación y minuta de revisión por la dirección (QDV-RG-PG-07_01).

Revision ID: 20261124_firmas_capacitacion_revdir
Revises: 20261106_desarrollo_produccion
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261124_firmas_capacitacion_revdir"
down_revision: str | None = "20261106_desarrollo_produccion"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    cols = {c["name"] for c in insp.get_columns("capacitaciones")} if "capacitaciones" in tables else set()
    if "capacitaciones" in tables and "disertante_firma" not in cols:
        op.add_column("capacitaciones", sa.Column("disertante_firma", sa.Text(), nullable=False, server_default="{}"))
    if "revisiones_direccion" not in tables:
        op.create_table(
            "revisiones_direccion",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=True),
            sa.Column("temas", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("participantes", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("acciones", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_revisiones_direccion_numero", "revisiones_direccion", ["numero"])
    if "revisiones_direccion_cambios" not in tables:
        op.create_table(
            "revisiones_direccion_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("revision_id", sa.Integer(), sa.ForeignKey("revisiones_direccion.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_revisiones_direccion_cambios_revision_id", "revisiones_direccion_cambios", ["revision_id"])
        op.create_index("ix_revisiones_direccion_cambios_created_at", "revisiones_direccion_cambios", ["created_at"])


def downgrade():
    op.drop_table("revisiones_direccion_cambios")
    op.drop_table("revisiones_direccion")
    op.drop_column("capacitaciones", "disertante_firma")
