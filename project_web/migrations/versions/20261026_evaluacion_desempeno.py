"""Evaluación de desempeño (QDV-RG-PG-05_04).

Revision ID: 20261026_evaluacion_desempeno
Revises: 20261026_minuta_reunion
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261026_evaluacion_desempeno"
down_revision: str | None = "20261026_minuta_reunion"
branch_labels: str | None = None
depends_on: str | None = None


def _txt(nombre, largo=None, default=""):
    tipo = sa.String(length=largo) if largo else sa.Text()
    return sa.Column(nombre, tipo, nullable=False, server_default=default)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "evaluaciones_desempeno" not in tables:
        op.create_table(
            "evaluaciones_desempeno",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("empleado_id", sa.Integer(), nullable=True),
            _txt("sector", 128),
            _txt("puesto", 128),
            _txt("evaluado", 255),
            _txt("periodo", 80),
            _txt("evaluador", 255),
            sa.Column("fecha", sa.Date(), nullable=True),
            _txt("puntajes", default="{}"),
            _txt("comentarios_evaluador"),
            _txt("comentarios_evaluado"),
            _txt("observaciones"),
            _txt("objetivos"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["empleado_id"], ["personal_empleados.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_evaluaciones_desempeno_numero", "evaluaciones_desempeno", ["numero"])
        op.create_index("ix_evaluaciones_desempeno_empleado_id", "evaluaciones_desempeno", ["empleado_id"])
    if "evaluaciones_desempeno_cambios" not in tables:
        op.create_table(
            "evaluaciones_desempeno_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("evaluacion_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["evaluacion_id"], ["evaluaciones_desempeno.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_evaluaciones_desempeno_cambios_evaluacion_id", "evaluaciones_desempeno_cambios", ["evaluacion_id"])
        op.create_index("ix_evaluaciones_desempeno_cambios_created_at", "evaluaciones_desempeno_cambios", ["created_at"])


def downgrade():
    op.drop_table("evaluaciones_desempeno_cambios")
    op.drop_table("evaluaciones_desempeno")
