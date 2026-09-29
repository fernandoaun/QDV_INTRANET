"""Constancia de entrega EPP (Res. 299/11): tipo/modelo, marca y certificación por entrega,
descripción del puesto y EPP asignados por trabajador.

Revision ID: 20260929_epp_constancia
Revises: 20260929_programas_tipo
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20260929_epp_constancia"
down_revision: str | None = "20260929_programas_tipo"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    ecols = {c["name"] for c in insp.get_columns("personal_entregas_epp")}
    for name, length in (("tipo_modelo", 128), ("marca", 128), ("certificacion", 2)):
        if name not in ecols:
            op.add_column("personal_entregas_epp", sa.Column(name, sa.String(length=length), nullable=False, server_default=""))
    pcols = {c["name"] for c in insp.get_columns("personal_empleados")}
    if "epp_descripcion_puesto" not in pcols:
        op.add_column(
            "personal_empleados", sa.Column("epp_descripcion_puesto", sa.String(length=2000), nullable=False, server_default="")
        )
    if "personal_epp_asignaciones" not in set(insp.get_table_names()):
        op.create_table(
            "personal_epp_asignaciones",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("empleado_id", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["empleado_id"], ["personal_empleados.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["item_id"], ["personal_epp_items.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("empleado_id", "item_id", name="uq_personal_epp_asig_emp_item"),
        )
        op.create_index("ix_personal_epp_asignaciones_empleado_id", "personal_epp_asignaciones", ["empleado_id"])
        op.create_index("ix_personal_epp_asignaciones_item_id", "personal_epp_asignaciones", ["item_id"])


def downgrade():
    op.drop_table("personal_epp_asignaciones")
    op.drop_column("personal_empleados", "epp_descripcion_puesto")
    for name in ("certificacion", "marca", "tipo_modelo"):
        op.drop_column("personal_entregas_epp", name)
