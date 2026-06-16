"""Vincular legajos de Personal con usuarios del sistema.

Revision ID: 20260616_personal_empleado_user
Revises: 20260616_stock_critical_alert_emails
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260616_personal_empleado_user"
down_revision: Union[str, Sequence[str], None] = "20260616_stock_critical_alert_emails"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _split_nombre_completo(full: str | None, fallback: str) -> tuple[str, str]:
    s = (full or "").strip()
    if not s:
        return fallback, ""
    if "," in s:
        ap, nom = [p.strip() for p in s.split(",", 1)]
        return ap or fallback, nom
    parts = s.split(None, 1)
    if len(parts) == 1:
        return fallback, parts[0]
    return parts[1], parts[0]


def upgrade() -> None:
    op.add_column("personal_empleados", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index("ix_personal_empleados_user_id", "personal_empleados", ["user_id"], unique=True)
    op.create_foreign_key(
        "fk_personal_empleados_user_id",
        "personal_empleados",
        "usuarios",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    conn = op.get_bind()
    users = conn.execute(sa.text("SELECT id, username, nombre_completo, activo FROM usuarios")).fetchall()
    linked_user_ids = {
        row[0]
        for row in conn.execute(
            sa.text("SELECT user_id FROM personal_empleados WHERE user_id IS NOT NULL")
        ).fetchall()
    }
    used_legajos = {
        row[0]
        for row in conn.execute(sa.text("SELECT legajo FROM personal_empleados")).fetchall()
    }

    for user_id, username, nombre_completo, activo in users:
        if user_id in linked_user_ids:
            continue
        apellido, nombre = _split_nombre_completo(nombre_completo, username or "Sin nombre")
        legajo = (username or f"U{user_id}").strip()[:32]
        orphan = conn.execute(
            sa.text(
                "SELECT id FROM personal_empleados WHERE user_id IS NULL AND lower(legajo) = lower(:legajo) LIMIT 1"
            ),
            {"legajo": legajo},
        ).fetchone()
        if orphan is not None:
            conn.execute(
                sa.text("UPDATE personal_empleados SET user_id = :user_id WHERE id = :emp_id"),
                {"user_id": user_id, "emp_id": orphan[0]},
            )
            linked_user_ids.add(user_id)
            continue
        if legajo in used_legajos:
            legajo = f"U{user_id}"[:32]
        used_legajos.add(legajo)
        estado = "activo" if activo else "baja"
        conn.execute(
            sa.text(
                """
                INSERT INTO personal_empleados (
                    user_id, legajo, dni, cuil, apellido, nombre, domicilio, telefono, email,
                    puesto, area, estado, talle_pantalon, talle_camisa, talle_calzado,
                    talle_guantes, talle_casco, observaciones, created_at, updated_at
                ) VALUES (
                    :user_id, :legajo, '', '', :apellido, :nombre, '', '', '',
                    '', '', :estado, '', '', '', '', '', '',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "user_id": user_id,
                "legajo": legajo,
                "apellido": apellido[:128],
                "nombre": nombre[:128],
                "estado": estado,
            },
        )


def downgrade() -> None:
    op.drop_constraint("fk_personal_empleados_user_id", "personal_empleados", type_="foreignkey")
    op.drop_index("ix_personal_empleados_user_id", table_name="personal_empleados")
    op.drop_column("personal_empleados", "user_id")
