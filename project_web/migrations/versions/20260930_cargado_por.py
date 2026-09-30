"""«Cargado por» en análisis y movimientos de stock (perfil Responsable de laboratorio).

Revision ID: 20260930_cargado_por
Revises: 20260929_fichas_proceso
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20260930_cargado_por"
down_revision: str | None = "20260929_fichas_proceso"
branch_labels: str | None = None
depends_on: str | None = None

TABLAS = (
    "salmuera_registros",
    "filtro_lavado_registros",
    "reactor_registros",
    "salmuera_analisis_8hs",
    "agua_registros",
    "consumos_stock",
    "stock_ajustes",
)


def upgrade():
    insp = sa.inspect(op.get_bind())
    for t in TABLAS:
        if "cargado_por_user_id" in {c["name"] for c in insp.get_columns(t)}:
            continue
        with op.batch_alter_table(t) as b:
            b.add_column(sa.Column("cargado_por_user_id", sa.Integer(), nullable=True))
            b.create_foreign_key(f"fk_{t}_cargado_por", "usuarios", ["cargado_por_user_id"], ["id"], ondelete="SET NULL")


def downgrade():
    for t in TABLAS:
        with op.batch_alter_table(t) as b:
            b.drop_constraint(f"fk_{t}_cargado_por", type_="foreignkey")
            b.drop_column("cargado_por_user_id")
