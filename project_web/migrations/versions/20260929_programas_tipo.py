"""Programas del PG-02: tipo (objetivos, cmass, …) y observaciones por fila.

Revision ID: 20260929_programas_tipo
Revises: 20260929_objetivos
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20260929_programas_tipo"
down_revision: str | None = "20260929_objetivos"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("objetivos_programas")}
    uniques = {u["name"] for u in insp.get_unique_constraints("objetivos_programas")}
    with op.batch_alter_table("objetivos_programas") as b:
        if "tipo" not in cols:
            b.add_column(sa.Column("tipo", sa.String(length=32), nullable=False, server_default="objetivos"))
            b.create_index("ix_objetivos_programas_tipo", ["tipo"])
        # El año deja de ser único solo: ahora es único por tipo de programa.
        for name in uniques:
            if name and name != "uq_objetivos_programas_tipo_anio":
                b.drop_constraint(name, type_="unique")
        if "uq_objetivos_programas_tipo_anio" not in uniques:
            b.create_unique_constraint("uq_objetivos_programas_tipo_anio", ["tipo", "anio"])
    ocols = {c["name"] for c in insp.get_columns("objetivos")}
    if "observaciones" not in ocols:
        op.add_column("objetivos", sa.Column("observaciones", sa.Text(), nullable=False, server_default=""))


def downgrade():
    op.drop_column("objetivos", "observaciones")
    with op.batch_alter_table("objetivos_programas") as b:
        b.drop_constraint("uq_objetivos_programas_tipo_anio", type_="unique")
        b.create_unique_constraint("objetivos_programas_anio_key", ["anio"])
        b.drop_index("ix_objetivos_programas_tipo")
        b.drop_column("tipo")
