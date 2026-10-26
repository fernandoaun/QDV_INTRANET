"""FODA (registro SGI QDV-RG-PG-09_01): matriz única de la empresa, editable, con historial por cuadrante."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import Foda, FodaCambio
from app.services.fichas_proceso_service import fecha_local, items
from app.services.plan_accion_service import fecha_dmy
from app.utils.datetime_operacion import operacion_zoneinfo

REGISTRO = {
    "codigo": "QDV-RG-PG-09_01",
    "titulo": "FODA",
    "fecha_vigencia": date(2026, 5, 20),
    "revision": "00",
}
# Cuadrantes en el orden de la matriz: internos arriba, externos abajo.
CUADRANTES: tuple[tuple[str, str], ...] = (
    ("fortalezas", "Fortalezas"),
    ("debilidades", "Debilidades"),
    ("oportunidades", "Oportunidades"),
    ("amenazas", "Amenazas"),
)
CAMPO_LABELS: dict[str, str] = dict(CUADRANTES)


def labels_context() -> dict[str, Any]:
    return {"reg": REGISTRO, "cuadrantes": CUADRANTES, "foda_campo_labels": CAMPO_LABELS, "items": items,
            "fecha_local": fecha_local, "fecha_dmy": fecha_dmy}


def get() -> Foda | None:
    return db.session.scalar(select(Foda).order_by(Foda.id).limit(1))


def ultima_actualizacion() -> date | None:
    ult = db.session.scalar(select(func.max(FodaCambio.created_at)))
    return ult.astimezone(operacion_zoneinfo()).date() if ult is not None else None


def cambios(limit: int = 200) -> list[FodaCambio]:
    return list(
        db.session.scalars(
            select(FodaCambio).order_by(FodaCambio.created_at.desc(), FodaCambio.id.desc()).limit(limit)
        ).unique()
    )


def guardar(data: Any, user_id: int | None) -> int:
    """Guarda los cuadrantes (un ítem por renglón) y devuelve cuántos cambiaron."""
    f = get()
    if f is None:
        f = Foda()
        db.session.add(f)
        db.session.flush()
    n = 0
    for campo, _ in CUADRANTES:
        nuevo = "\n".join(items(str(data.get(campo) or "")))
        antes = getattr(f, campo) or ""
        if nuevo == antes:
            continue
        setattr(f, campo, nuevo)
        db.session.add(FodaCambio(foda_id=f.id, user_id=user_id, campo=campo, antes=antes or None, despues=nuevo or None))
        n += 1
    return n
