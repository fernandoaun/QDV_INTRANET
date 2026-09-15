"""Permisos por puesto del organigrama y catálogo de recursos conocidos.

Revision ID: 20260915_puesto_perm
Revises: 20260910_whatsapp
Create Date: 2026-09-15
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision: str = "20260915_puesto_perm"
down_revision: str | None = "20260910_whatsapp"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "permisos_puesto" not in tables:
        op.create_table(
            "permisos_puesto",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("puesto_id", sa.String(length=64), nullable=False),
            sa.Column("permiso", sa.String(length=64), nullable=False),
            sa.Column("habilitado", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("puede_editar", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("puesto_id", "permiso", name="uq_permiso_puesto_perm"),
        )
        op.create_index("ix_permisos_puesto_puesto_id", "permisos_puesto", ["puesto_id"])

    if "permisos_recursos_conocidos" not in tables:
        op.create_table(
            "permisos_recursos_conocidos",
            sa.Column("permiso", sa.String(length=64), nullable=False),
            sa.Column("reconocido_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("permiso"),
        )

    from app.constants import PERMISSION_KEYS

    n = bind.execute(sa.text("SELECT COUNT(*) FROM permisos_recursos_conocidos")).scalar()
    if int(n or 0) == 0 and PERMISSION_KEYS:
        now = datetime.now(timezone.utc)
        op.bulk_insert(
            sa.table(
                "permisos_recursos_conocidos",
                sa.column("permiso", sa.String),
                sa.column("reconocido_at", sa.DateTime(timezone=True)),
            ),
            [{"permiso": key, "reconocido_at": now} for key in PERMISSION_KEYS],
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "permisos_recursos_conocidos" in tables:
        op.drop_table("permisos_recursos_conocidos")
    if "permisos_puesto" in tables:
        indexes = {i["name"] for i in insp.get_indexes("permisos_puesto")}
        if "ix_permisos_puesto_puesto_id" in indexes:
            op.drop_index("ix_permisos_puesto_puesto_id", table_name="permisos_puesto")
        op.drop_table("permisos_puesto")
