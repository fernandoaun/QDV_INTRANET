"""Perfiles de puesto (QDV-RG-PG-05_01).

Revision ID: 20261019_perfiles_puesto
Revises: 20261014_entrega_agua_litros
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261019_perfiles_puesto"
down_revision: str | None = "20261014_entrega_agua_litros"
branch_labels: str | None = None
depends_on: str | None = None

_LISTAS = (
    "supervisa_a", "interactua_con", "tareas", "educacion", "formacion", "idiomas_otros",
    "experiencia", "habilidades", "autoridad", "rendicion_cuentas",
)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "perfiles_puesto" not in tables:
        op.create_table(
            "perfiles_puesto",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("puesto", sa.String(length=160), nullable=False),
            sa.Column("proceso", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("supervisor", sa.String(length=160), nullable=False, server_default=""),
            *[sa.Column(c, sa.Text(), nullable=False, server_default="") for c in _LISTAS],
            sa.Column("aprobado_por", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("fecha_actualizacion", sa.Date(), nullable=True),
            sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "perfiles_puesto_cambios" not in tables:
        op.create_table(
            "perfiles_puesto_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("perfil_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["perfil_id"], ["perfiles_puesto.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_perfiles_puesto_cambios_perfil_id", "perfiles_puesto_cambios", ["perfil_id"])
        op.create_index("ix_perfiles_puesto_cambios_created_at", "perfiles_puesto_cambios", ["created_at"])


def downgrade():
    op.drop_table("perfiles_puesto_cambios")
    op.drop_table("perfiles_puesto")
