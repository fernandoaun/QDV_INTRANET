"""Matriz de riesgos y oportunidades (QDV-RG-PG-09_04), una hoja por sector.

Si en los archivos subidos está la planilla original (una pestaña por sector), se importa.

Revision ID: 20261026_matriz_riesgos
Revises: 20261026_matriz_legal
Create Date: 2026-10-26
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision: str = "20261026_matriz_riesgos"
down_revision: str | None = "20261026_matriz_legal"
branch_labels: str | None = None
depends_on: str | None = None


def _importar_planilla():
    """Busca la planilla QDV-RG-PG-09_04 entre los archivos del SGI y carga sus pestañas. Nunca frena la migración."""
    raiz = (os.environ.get("APP_UPLOAD_ROOT") or "").strip()
    if not raiz or not (Path(raiz) / "archivo").is_dir():
        return
    try:
        from app.services.matriz_riesgos_service import leer_xlsx

        mejor = []
        for p in sorted((Path(raiz) / "archivo").rglob("*.xlsx"), key=lambda x: x.stat().st_mtime):
            try:
                hojas = leer_xlsx(p)
            except Exception:  # noqa: BLE001 — cualquier otra planilla
                continue
            if len(hojas) >= len(mejor) and hojas:
                mejor = hojas
        if not mejor:
            return
        bind = op.get_bind()
        ahora = datetime.now(timezone.utc)
        with bind.begin_nested():  # si algo falla, se descarta solo la importación
            _insertar(bind, mejor, ahora)
    except Exception as exc:  # noqa: BLE001
        print(f"matriz_riesgos: no se importó la planilla ({exc})")


def _insertar(bind, mejor, ahora):
    for orden, h in enumerate(mejor, 1):
        mid = bind.execute(
            sa.text(
                "INSERT INTO matriz_riesgos (sector, fecha_actualizacion, filas, orden, activo, created_at, updated_at) "
                "VALUES (:s, :f, :filas, :o, true, :a, :a) RETURNING id"
            ),
            {"s": h["sector"][:160], "f": h["fecha_actualizacion"], "filas": json.dumps(h["filas"], ensure_ascii=False),
             "o": orden, "a": ahora},
        ).scalar()
        bind.execute(
            sa.text(
                "INSERT INTO matriz_riesgos_cambios (matriz_id, campo, despues, created_at) VALUES (:m, 'alta', :d, :a)"
            ),
            {"m": mid, "d": f"{h['sector']}: {len(h['filas'])} renglón(es), importado de la planilla Excel", "a": ahora},
        )


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "matriz_riesgos" not in tables:
        op.create_table(
            "matriz_riesgos",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("sector", sa.String(length=160), nullable=False),
            sa.Column("fecha_actualizacion", sa.Date(), nullable=True),
            sa.Column("filas", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_matriz_riesgos_sector", "matriz_riesgos", ["sector"])
    if "matriz_riesgos_cambios" not in tables:
        op.create_table(
            "matriz_riesgos_cambios",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("matriz_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("campo", sa.String(length=32), nullable=False),
            sa.Column("antes", sa.Text(), nullable=True),
            sa.Column("despues", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["matriz_id"], ["matriz_riesgos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_matriz_riesgos_cambios_matriz_id", "matriz_riesgos_cambios", ["matriz_id"])
        op.create_index("ix_matriz_riesgos_cambios_created_at", "matriz_riesgos_cambios", ["created_at"])
    if "matriz_riesgos" not in tables and op.get_bind().dialect.name == "postgresql":
        _importar_planilla()


def downgrade():
    op.drop_table("matriz_riesgos_cambios")
    op.drop_table("matriz_riesgos")
