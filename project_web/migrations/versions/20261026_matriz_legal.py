"""Matriz legal y otros requisitos (QDV-RG-PG-10_01).

Revision ID: 20261026_matriz_legal
Revises: 20261026_foda
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261026_matriz_legal"
down_revision: str | None = "20261026_foda"
branch_labels: str | None = None
depends_on: str | None = None


def _txt(nombre, largo=None):
    tipo = sa.String(length=largo) if largo else sa.Text()
    return sa.Column(nombre, tipo, nullable=False, server_default="")


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "matriz_legal" not in tables:
        op.create_table(
            "matriz_legal",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ambito", sa.String(length=20), nullable=False),
            _txt("tipo", 80),
            _txt("fuente", 160),
            _txt("organismo", 160),
            _txt("norma", 255),
            _txt("articulo", 160),
            _txt("descripcion"),
            _txt("proceso", 160),
            _txt("responsable", 160),
            _txt("evidencia"),
            _txt("frecuencia", 80),
            _txt("estado", 40),
            _txt("observaciones"),
            sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_matriz_legal_ambito", "matriz_legal", ["ambito"])
    if "matriz_legal_cambios" not in tables:
        op.create_table(
            "matriz_legal_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("requisito_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["requisito_id"], ["matriz_legal.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_matriz_legal_cambios_requisito_id", "matriz_legal_cambios", ["requisito_id"])
        op.create_index("ix_matriz_legal_cambios_created_at", "matriz_legal_cambios", ["created_at"])


def downgrade():
    op.drop_table("matriz_legal_cambios")
    op.drop_table("matriz_legal")
