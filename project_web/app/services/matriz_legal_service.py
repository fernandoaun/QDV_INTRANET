"""Matriz legal y otros requisitos (registro SGI QDV-RG-PG-10_01): un requisito por fila, en tres hojas por ámbito."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import FichaProceso, RequisitoLegal, RequisitoLegalCambio
from app.services.fichas_proceso_service import fecha_local
from app.services.plan_accion_service import fecha_dmy
from app.utils.datetime_operacion import operacion_zoneinfo

REGISTRO = {
    "codigo": "QDV-RG-PG-10_01",
    "titulo": "MATRIZ LEGAL Y OTROS REQUISITOS",
    "fecha_vigencia": date(2026, 7, 21),
    "revision": "00",
}
# Hojas de la planilla.
AMBITOS: dict[str, str] = {"nacion": "Nación", "rn": "Río Negro", "otros": "Otros requisitos"}
COLUMNAS: tuple[str, ...] = (
    "tipo", "fuente", "organismo", "norma", "articulo", "descripcion", "proceso", "responsable", "evidencia",
    "frecuencia", "estado", "observaciones",
)
CAMPO_LABELS: dict[str, str] = {
    "ambito": "Hoja",
    "tipo": "Tipo de requisito",
    "fuente": "Fuente",
    "organismo": "Organismo emisor",
    "norma": "Norma / Ley / Contrato",
    "articulo": "Art./Ref.",
    "descripcion": "Descripción del requisito",
    "proceso": "Proceso",
    "responsable": "Responsable",
    "evidencia": "Evidencia objetiva",
    "frecuencia": "Frecuencia",
    "estado": "Estado",
    "observaciones": "Observaciones",
    "alta": "Alta",
    "baja": "Baja",
}
# Sugerencias (el campo admite otro valor).
OPCIONES: dict[str, tuple[str, ...]] = {
    "tipo": ("Legal", "Reglamentario", "Contractual", "Cliente", "Otros requisitos"),
    "frecuencia": ("Permanente", "Única vez", "Mensual", "Trimestral", "Semestral", "Anual", "Bianual", "Según vencimiento"),
    "estado": ("Cumple", "En proceso", "No cumple", "No aplica"),
}
_LARGOS = {"tipo": 80, "fuente": 160, "organismo": 160, "norma": 255, "articulo": 160, "proceso": 160,
           "responsable": 160, "frecuencia": 80, "estado": 40}


def procesos() -> list[str]:
    """Procesos de las fichas de proceso (QDV-RG-PG-09_03), para elegir en la columna Proceso."""
    return list(
        db.session.scalars(
            select(FichaProceso.proceso).where(FichaProceso.activo.is_(True)).order_by(FichaProceso.orden, FichaProceso.proceso)
        )
    )


def labels_context() -> dict[str, Any]:
    return {"reg": REGISTRO, "ambitos": AMBITOS, "columnas": COLUMNAS, "ml_campo_labels": CAMPO_LABELS,
            "opciones": OPCIONES, "fecha_local": fecha_local, "fecha_dmy": fecha_dmy}


def listar(ambito: str) -> list[RequisitoLegal]:
    return list(
        db.session.scalars(
            select(RequisitoLegal)
            .where(RequisitoLegal.activo.is_(True), RequisitoLegal.ambito == ambito)
            .order_by(RequisitoLegal.orden, RequisitoLegal.id)
        )
    )


def contar() -> dict[str, int]:
    rows = db.session.execute(
        select(RequisitoLegal.ambito, func.count()).where(RequisitoLegal.activo.is_(True)).group_by(RequisitoLegal.ambito)
    )
    return {a: n for a, n in rows}


def get(requisito_id: int) -> RequisitoLegal | None:
    r = db.session.get(RequisitoLegal, int(requisito_id))
    return r if r is not None and r.activo else None


def ultima_actualizacion() -> tuple[date | None, str]:
    """Fecha y usuario del último cambio de la matriz (encabezado de cada hoja)."""
    ult = db.session.scalar(select(RequisitoLegalCambio).order_by(RequisitoLegalCambio.created_at.desc()).limit(1))
    if ult is None:
        return None, ""
    return ult.created_at.astimezone(operacion_zoneinfo()).date(), (ult.user.username if ult.user else "")


def cambios(r: RequisitoLegal, limit: int = 100) -> list[RequisitoLegalCambio]:
    return list(
        db.session.scalars(
            select(RequisitoLegalCambio)
            .where(RequisitoLegalCambio.requisito_id == r.id)
            .order_by(RequisitoLegalCambio.created_at.desc(), RequisitoLegalCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(r: RequisitoLegal, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        RequisitoLegalCambio(
            requisito_id=r.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes in (None, "") else str(antes),
            despues=None if despues in (None, "") else str(despues),
        )
    )


def _limpio(data: Any) -> tuple[dict[str, Any], list[str]]:
    v: dict[str, Any] = {}
    errores: list[str] = []
    for k in COLUMNAS:
        val = str(data.get(k) or "").strip()
        if k in _LARGOS:
            val = re.sub(r"\s+", " ", val)[: _LARGOS[k]]
        if k in OPCIONES and val:
            val = next((o for o in OPCIONES[k] if o.lower() == val.lower()), val)
        v[k] = val
    v["ambito"] = str(data.get("ambito") or "").strip()
    if v["ambito"] not in AMBITOS:
        errores.append("Elegí la hoja: Nación, Río Negro u Otros requisitos.")
    if not v["norma"] and not v["descripcion"]:
        errores.append("Completá la norma / ley / contrato o la descripción del requisito.")
    return v, errores


def guardar(r: RequisitoLegal, data: Any, user_id: int | None) -> list[str]:
    v, errores = _limpio(data)
    if errores:
        return errores
    for campo, nuevo in v.items():
        antes = getattr(r, campo)
        if (antes or None) == (nuevo or None):
            continue
        setattr(r, campo, nuevo)
        if campo == "ambito":
            antes, nuevo = AMBITOS.get(antes, antes), AMBITOS[nuevo]
        _log(r, user_id, campo, antes, nuevo)
    return []


def crear(data: Any, user_id: int | None) -> tuple[RequisitoLegal | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    orden = (db.session.scalar(select(func.max(RequisitoLegal.orden)).where(RequisitoLegal.ambito == v["ambito"])) or 0) + 1
    r = RequisitoLegal(orden=orden, **v)
    db.session.add(r)
    db.session.flush()
    _log(r, user_id, "alta", None, f"{AMBITOS[r.ambito]}: {r.norma or r.descripcion[:120]}")
    return r, []


def baja(r: RequisitoLegal, user_id: int | None) -> None:
    r.activo = False
    _log(r, user_id, "baja", f"{AMBITOS[r.ambito]}: {r.norma or r.descripcion[:120]}", None)
