"""FODA (QDV-RG-PG-09_01).

Revision ID: 20261026_foda
Revises: 20261026_desvios
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261026_foda"
down_revision: str | None = "20261026_desvios"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "foda" not in tables:
        op.create_table(
            "foda",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            *[sa.Column(c, sa.Text(), nullable=False, server_default="") for c in ("fortalezas", "oportunidades", "debilidades", "amenazas")],
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "foda_cambios" not in tables:
        op.create_table(
            "foda_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("foda_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["foda_id"], ["foda.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_foda_cambios_foda_id", "foda_cambios", ["foda_id"])
        op.create_index("ix_foda_cambios_created_at", "foda_cambios", ["created_at"])


def downgrade():
    op.drop_table("foda_cambios")
    op.drop_table("foda")
