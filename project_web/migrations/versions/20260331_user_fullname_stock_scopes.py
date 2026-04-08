"""usuarios.nombre_completo + permisos internos de stock

Revision ID: 20260331_user_fullname_stock_scopes
Revises: 20260331_permiso_puede_editar
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260331_user_fullname_stock_scopes"
down_revision: Union[str, Sequence[str], None] = "20260331_permiso_puede_editar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns(table_name)}
    return column_name in cols


def _perm_exists(conn: sa.Connection, user_id: int, perm: str) -> bool:
    q = sa.text(
        "SELECT 1 FROM permisos_usuario WHERE user_id = :uid AND permiso = :perm LIMIT 1"
    )
    return conn.execute(q, {"uid": int(user_id), "perm": str(perm)}).first() is not None


def _insert_perm(conn: sa.Connection, user_id: int, perm: str, can_edit: bool) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO permisos_usuario (user_id, permiso, habilitado, puede_editar)
            VALUES (:uid, :perm, :hab, :edit)
            """
        ),
        {
            "uid": int(user_id),
            "perm": str(perm),
            "hab": True,
            "edit": bool(can_edit),
        },
    )


def upgrade() -> None:
    if not _column_exists("usuarios", "nombre_completo"):
        op.add_column("usuarios", sa.Column("nombre_completo", sa.String(length=256), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT user_id, permiso, puede_editar
            FROM permisos_usuario
            WHERE habilitado IS true
              AND permiso IN ('bolson_registro', 'bolson_carga')
            """
        )
    ).fetchall()

    for user_id, permiso, puede_editar in rows:
        can_edit = bool(puede_editar)
        if str(permiso) == "bolson_registro":
            targets = (
                "stock_hub",
                "stock_ingreso_mp",
                "stock_ingreso_lab",
                "stock_existencias",
                "stock_historial",
            )
        else:
            targets = ("stock_hub", "stock_consumos")
        for target in targets:
            if not _perm_exists(conn, int(user_id), target):
                _insert_perm(conn, int(user_id), target, can_edit)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM permisos_usuario
            WHERE permiso IN (
              'stock_hub',
              'stock_ingreso_mp',
              'stock_ingreso_lab',
              'stock_consumos',
              'stock_existencias',
              'stock_historial',
              'stock_alertas_config'
            )
            """
        )
    )
    if _column_exists("usuarios", "nombre_completo"):
        op.drop_column("usuarios", "nombre_completo")
