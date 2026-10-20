"""Plan de acción (QDV-RG-PG-02_03).

Revision ID: 20261020_plan_accion
Revises: 20261020_usuario_email
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261020_plan_accion"
down_revision: str | None = "20261020_usuario_email"
branch_labels: str | None = None
depends_on: str | None = None


def _txt(nombre, largo=None):
    tipo = sa.String(length=largo) if largo else sa.Text()
    return sa.Column(nombre, tipo, nullable=False, server_default="")


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "plan_accion" not in tables:
        op.create_table(
            "plan_accion",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            _txt("origen", 80),
            _txt("tipo_hallazgo", 80),
            sa.Column("fecha_deteccion", sa.Date(), nullable=True),
            _txt("tipo_accion", 80),
            _txt("accion"),
            _txt("causa_raiz", 20),
            _txt("causa_raiz_descripcion"),
            _txt("requisito", 255),
            sa.Column("fecha_cumplimiento", sa.Date(), nullable=True),
            _txt("estado", 20),
            _txt("responsable", 255),
            _txt("metodo_eficacia"),
            _txt("resultado_eficacia", 20),
            _txt("comentarios"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_plan_accion_numero", "plan_accion", ["numero"])
    if "plan_accion_cambios" not in tables:
        op.create_table(
            "plan_accion_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("accion_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["accion_id"], ["plan_accion.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_plan_accion_cambios_accion_id", "plan_accion_cambios", ["accion_id"])
        op.create_index("ix_plan_accion_cambios_created_at", "plan_accion_cambios", ["created_at"])


def downgrade():
    op.drop_table("plan_accion_cambios")
    op.drop_table("plan_accion")
