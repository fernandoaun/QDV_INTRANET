from __future__ import annotations

from sqlalchemy import func, inspect, select, text

from app.extensions import db
from app.models import ColumnaIntercambio, Operador

from app.constants import DEFAULT_OPERATORS
from app.utils.datetime_operacion import now_operacion_local_iso_seconds, now_operacion_naive_local


def ensure_local_sqlite_schema() -> None:
    """Completa columnas/tablas nuevas en SQLite local si Alembic no corrió."""
    if db.engine.dialect.name != "sqlite":
        return
    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    if "usuarios" in tables:
        cols = {c["name"] for c in insp.get_columns("usuarios")}
        if "whatsapp_e164" not in cols:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE usuarios ADD COLUMN whatsapp_e164 VARCHAR(20)"))
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_usuarios_whatsapp_e164 "
                        "ON usuarios (whatsapp_e164)"
                    )
                )
    try:
        from app.services import permiso_asignacion_service as perm_asig

        perm_asig.ensure_schema()
    except Exception:
        db.session.rollback()
    if "filtro_lavado_registros" not in tables:
        with db.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS filtro_lavado_registros ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "fecha_iso VARCHAR(16) NOT NULL, "
                    "hora_hm VARCHAR(8) NOT NULL, "
                    "operador VARCHAR(256) NOT NULL, "
                    "observaciones TEXT, "
                    "created_at_iso VARCHAR(32) NOT NULL)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_filtro_lavado_registros_fecha_iso "
                    "ON filtro_lavado_registros (fecha_iso)"
                )
            )


def ensure_seed_data() -> None:
    """Operadores por defecto y filas iniciales de columnas (paridad con app de escritorio)."""
    ensure_local_sqlite_schema()
    n_op = db.session.scalar(select(func.count()).select_from(Operador)) or 0
    if n_op == 0:
        now = now_operacion_local_iso_seconds()
        for name in DEFAULT_OPERATORS:
            db.session.add(Operador(nombre=name, created_at_iso=now))
        db.session.commit()

    for col in (1, 2, 3):
        cnt = db.session.scalar(
            select(func.count()).select_from(ColumnaIntercambio).where(ColumnaIntercambio.columna_numero == col)
        )
        if int(cnt or 0) > 0:
            continue
        now = now_operacion_naive_local()
        now_iso = now.isoformat(timespec="seconds")
        fecha_h = now.strftime("%d/%m/%Y")
        hora_h = now.strftime("%H:%M")
        defaults = {
            1: ("En operación", None, None),
            2: ("Regenerada", fecha_h, hora_h),
            3: ("Regenerada", fecha_h, hora_h),
        }
        estado, fr, hr = defaults[col]
        db.session.add(
            ColumnaIntercambio(
                columna_numero=col,
                estado=estado,
                fecha_regeneracion=fr,
                hora_regeneracion=hr,
                dureza_salida_ppm=None,
                dureza_post_regeneracion_ppm=None,
                observaciones="",
                created_at_iso=now_iso,
                updated_at_iso=now_iso,
            )
        )
    db.session.commit()
