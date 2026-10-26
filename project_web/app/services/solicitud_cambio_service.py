"""Solicitud de cambio (registro SGI QDV-RG-PG-03_01): una hoja por solicitud, editable, con historial."""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import SolicitudCambio, SolicitudCambioCambio
from app.services.fichas_proceso_service import fecha_local, items
from app.services.plan_accion_service import fecha_dmy, parse_fecha

REGISTRO = {
    "codigo": "QDV-RG-PG-03_01",
    "titulo": "SOLICITUD DEL CAMBIO",
    "fecha_vigencia": date(2026, 10, 20),
    "revision": "00",
}

# Casillas «Tipo de cambio» del formulario, en el orden de sus tres columnas.
TIPOS: tuple[str, ...] = (
    "Operativo",
    "Diseño",
    "Construcción",
    "RRHH - Personal",
    "Condiciones climáticas",
    "Por requerimiento de parte externa interesada",
    "Disturbios sociales",
    "Por reparaciones o contingencias",
    "Por requerimiento legal o normativo",
)
# Sugerencias (el campo admite otro valor).
OPCIONES: dict[str, tuple[str, ...]] = {
    "estado": ("Pendiente", "En evaluación", "Resuelta", "Cerrada"),
    "prioridad": ("Alta", "Media", "Baja"),
}
RESOLUCIONES: tuple[str, ...] = ("Aceptado", "Rechazado")
EFICACIA: tuple[str, ...] = ("Sí", "No")
CAMPOS_TEXTO: tuple[str, ...] = (
    "asunto", "solicita", "estado", "sector", "razon", "prioridad", "descripcion", "equipo_evaluacion", "impactos",
    "resolucion",
)
CAMPOS_FECHA: tuple[str, ...] = ("fecha", "requerido_para", "fecha_evaluacion", "fecha_resolucion")
CAMPO_LABELS: dict[str, str] = {
    "numero": "ID solicitud de cambio",
    "fecha": "Fecha",
    "asunto": "Asunto",
    "solicita": "Solicita",
    "estado": "Estado de la solicitud",
    "sector": "Obra / servicio / sector de planta",
    "requerido_para": "Requerido para",
    "razon": "Razón",
    "prioridad": "Prioridad",
    "descripcion": "Descripción del cambio",
    "tipos": "Tipo de cambio",
    "fecha_evaluacion": "Fecha de evaluación",
    "equipo_evaluacion": "Integrantes del equipo de evaluación del proyecto",
    "impactos": "Descripción de los impactos",
    "resolucion": "Resolución",
    "fecha_resolucion": "Fecha de resolución",
    "acciones_control": "Acciones de control",
    "alta": "Alta",
    "baja": "Baja",
}
_LARGOS = {"asunto": 255, "solicita": 255, "estado": 40, "sector": 255, "prioridad": 20, "resolucion": 20}
ACCION_CAMPOS: tuple[str, ...] = ("actividad", "responsable", "fecha", "eficacia")
FILAS_ACCIONES = 6  # renglones de la tabla del formulario


def acciones(s: SolicitudCambio | None) -> list[dict[str, str]]:
    if s is None:
        return []
    try:
        data = json.loads(s.acciones_control or "[]")
    except ValueError:
        return []
    return [a for a in data if isinstance(a, dict)]


def _acciones_txt(lista: list[dict[str, str]]) -> str:
    return "\n".join(" · ".join(a.get(k, "") or "—" for k in ACCION_CAMPOS) for a in lista)


def labels_context() -> dict[str, Any]:
    return {
        "reg": REGISTRO, "tipos_cambio": TIPOS, "opciones": OPCIONES, "resoluciones": RESOLUCIONES, "eficacia_op": EFICACIA,
        "sc_campo_labels": CAMPO_LABELS, "fecha_local": fecha_local, "fecha_dmy": fecha_dmy, "items": items,
        "acciones": acciones, "filas_acciones": FILAS_ACCIONES,
    }


def listar() -> list[SolicitudCambio]:
    return list(
        db.session.scalars(
            select(SolicitudCambio).where(SolicitudCambio.activo.is_(True)).order_by(SolicitudCambio.numero.desc())
        )
    )


def get(solicitud_id: int) -> SolicitudCambio | None:
    s = db.session.get(SolicitudCambio, int(solicitud_id))
    return s if s is not None and s.activo else None


def cambios(s: SolicitudCambio, limit: int = 100) -> list[SolicitudCambioCambio]:
    return list(
        db.session.scalars(
            select(SolicitudCambioCambio)
            .where(SolicitudCambioCambio.solicitud_id == s.id)
            .order_by(SolicitudCambioCambio.created_at.desc(), SolicitudCambioCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(s: SolicitudCambio, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        SolicitudCambioCambio(
            solicitud_id=s.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes in (None, "") else str(antes),
            despues=None if despues in (None, "") else str(despues),
        )
    )


def _opcion(valor: str, opciones: tuple[str, ...]) -> str:
    for op in opciones:
        if op.lower() == valor.lower():
            return op
    return valor


def _limpio(data: Any) -> tuple[dict[str, Any], list[str]]:
    v: dict[str, Any] = {}
    errores: list[str] = []
    for k in CAMPOS_TEXTO:
        val = str(data.get(k) or "").strip()
        if k in _LARGOS:
            val = re.sub(r"\s+", " ", val)[: _LARGOS[k]]
        if k in OPCIONES and val:
            val = _opcion(val, OPCIONES[k])
        v[k] = val
    if v["resolucion"] not in ("", *RESOLUCIONES):
        v["resolucion"] = _opcion(v["resolucion"], RESOLUCIONES)
        if v["resolucion"] not in RESOLUCIONES:
            errores.append("La resolución es «Aceptado» o «Rechazado».")
    for k in CAMPOS_FECHA:
        try:
            v[k] = parse_fecha(data.get(k))
        except ValueError:
            errores.append(f"{CAMPO_LABELS[k]}: fecha inválida, usá dd/mm/aaaa.")
            v[k] = None
    getlist = getattr(data, "getlist", None)
    marcados = getlist("tipos") if getlist else (data.get("tipos") or [])
    if isinstance(marcados, str):
        marcados = items(marcados)
    v["tipos"] = "\n".join(t for t in TIPOS if t in marcados)
    if getlist:  # formulario: renglones ac_<campo>_<i>
        crudas = [{k: data.get(f"ac_{k}_{i}") for k in ACCION_CAMPOS} for i in range(int(data.get("acciones_filas") or 0))]
    else:
        crudas = list(data.get("acciones_control") or [])
    filas: list[dict[str, str]] = []
    for i, cruda in enumerate(crudas):
        fila = {k: re.sub(r"\s+", " ", str(cruda.get(k) or "")).strip()[:255] for k in ACCION_CAMPOS}
        if not any(fila.values()):
            continue
        if fila["fecha"]:
            try:
                fila["fecha"] = fecha_dmy(parse_fecha(fila["fecha"]))
            except ValueError:
                errores.append(f"Acciones de control, renglón {i + 1}: fecha inválida, usá dd/mm/aaaa.")
        filas.append(fila)
    v["acciones_control"] = json.dumps(filas, ensure_ascii=False)
    if not v["asunto"]:
        errores.append("El asunto es obligatorio.")
    return v, errores


def _fmt(campo: str, val: Any) -> Any:
    if not val:
        return val
    if campo in CAMPOS_FECHA:
        return fecha_dmy(val)
    if campo == "acciones_control":
        try:
            return _acciones_txt(json.loads(val)) or None
        except ValueError:
            return val
    return val


def guardar(s: SolicitudCambio, data: Any, user_id: int | None) -> list[str]:
    v, errores = _limpio(data)
    if errores:
        return errores
    for campo, nuevo in v.items():
        antes = getattr(s, campo)
        if campo == "acciones_control" and json.loads(antes or "[]") == json.loads(nuevo):
            continue
        if (antes or None) == (nuevo or None):
            continue
        setattr(s, campo, nuevo)
        _log(s, user_id, campo, _fmt(campo, antes), _fmt(campo, nuevo))
    return []


def crear(data: Any, user_id: int | None) -> tuple[SolicitudCambio | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    numero = (db.session.scalar(select(func.max(SolicitudCambio.numero))) or 0) + 1
    s = SolicitudCambio(numero=numero, **v)
    db.session.add(s)
    db.session.flush()
    _log(s, user_id, "alta", None, f"N° {numero}: {s.asunto}")
    return s, []


def baja(s: SolicitudCambio, user_id: int | None) -> None:
    s.activo = False
    _log(s, user_id, "baja", f"N° {s.numero}: {s.asunto}", None)
