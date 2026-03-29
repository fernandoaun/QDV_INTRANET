from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.extensions import db
from app.models import ColumnaIntercambio, Operador

from app.constants import DEFAULT_OPERATORS


def ensure_seed_data() -> None:
    """Operadores por defecto y filas iniciales de columnas (paridad con app de escritorio)."""
    n_op = db.session.scalar(select(func.count()).select_from(Operador)) or 0
    if n_op == 0:
        now = datetime.now().isoformat(timespec="seconds")
        for name in DEFAULT_OPERATORS:
            db.session.add(Operador(nombre=name, created_at_iso=now))
        db.session.commit()

    for col in (1, 2, 3):
        cnt = db.session.scalar(
            select(func.count()).select_from(ColumnaIntercambio).where(ColumnaIntercambio.columna_numero == col)
        )
        if int(cnt or 0) > 0:
            continue
        now = datetime.now()
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
