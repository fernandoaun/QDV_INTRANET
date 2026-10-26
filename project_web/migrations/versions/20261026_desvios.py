"""Registro y seguimiento de NC, PNC y OM (QDV-RG-PG-08_01 y 08_02).

Revision ID: 20261026_desvios
Revises: 20261026_evaluacion_desempeno
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261026_desvios"
down_revision: str | None = "20261026_evaluacion_desempeno"
branch_labels: str | None = None
depends_on: str | None = None


def _txt(nombre, largo=None, default=""):
    tipo = sa.String(length=largo) if largo else sa.Text()
    return sa.Column(nombre, tipo, nullable=False, server_default=default)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "desvios" not in tables:
        op.create_table(
            "desvios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=True),
            _txt("clasificacion", 30),
            _txt("fuentes"),
            _txt("descripcion"),
            _txt("emisor", 255),
            _txt("encuadre"),
            _txt("requisito"),
            _txt("causa_raiz"),
            _txt("acciones_inmediatas", default="[]"),
            _txt("correcciones", default="[]"),
            _txt("acciones_correctivas", default="[]"),
            _txt("evidencia"),
            _txt("verificador", 255),
            _txt("implementadas", 2),
            sa.Column("fecha_implementacion", sa.Date(), nullable=True),
            _txt("eficaces", 2),
            sa.Column("fecha_eficacia", sa.Date(), nullable=True),
            _txt("cierre_responsables"),
            sa.Column("fecha_cierre", sa.Date(), nullable=True),
            _txt("estado", 30, default="Abierta"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_desvios_numero", "desvios", ["numero"])
    if "desvios_cambios" not in tables:
        op.create_table(
            "desvios_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("desvio_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["desvio_id"], ["desvios.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_desvios_cambios_desvio_id", "desvios_cambios", ["desvio_id"])
        op.create_index("ix_desvios_cambios_created_at", "desvios_cambios", ["created_at"])


def downgrade():
    op.drop_table("desvios_cambios")
    op.drop_table("desvios")
