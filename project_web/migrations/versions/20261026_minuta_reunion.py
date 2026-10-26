"""Minuta de reunión (QDV-RG-PG-04_01).

Revision ID: 20261026_minuta_reunion
Revises: 20261026_solicitud_cambio
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261026_minuta_reunion"
down_revision: str | None = "20261026_solicitud_cambio"
branch_labels: str | None = None
depends_on: str | None = None


def _txt(nombre, largo=None, default=""):
    tipo = sa.String(length=largo) if largo else sa.Text()
    return sa.Column(nombre, tipo, nullable=False, server_default=default)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "minutas_reunion" not in tables:
        op.create_table(
            "minutas_reunion",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=True),
            _txt("horario", 60),
            _txt("lugar", 255),
            _txt("motivo"),
            _txt("participantes", default="[]"),
            _txt("desarrollo"),
            _txt("acciones", default="[]"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_minutas_reunion_numero", "minutas_reunion", ["numero"])
    if "minutas_reunion_cambios" not in tables:
        op.create_table(
            "minutas_reunion_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("minuta_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["minuta_id"], ["minutas_reunion.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_minutas_reunion_cambios_minuta_id", "minutas_reunion_cambios", ["minuta_id"])
        op.create_index("ix_minutas_reunion_cambios_created_at", "minutas_reunion_cambios", ["created_at"])


def downgrade():
    op.drop_table("minutas_reunion_cambios")
    op.drop_table("minutas_reunion")
