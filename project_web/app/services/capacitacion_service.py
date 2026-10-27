"""Registro de capacitación (registro SGI QDV-RG-PG-05_03): una hoja por capacitación, editable, con historial."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import Capacitacion, CapacitacionCambio, EmpleadoPersonal
from app.services.fichas_proceso_service import fecha_local
from app.services.plan_accion_service import fecha_dmy, parse_fecha

REGISTRO = {
    "codigo": "QDV-RG-PG-05_03",
    "titulo": "REGISTRO DE CAPACITACIÓN",
    "fecha_vigencia": date(2026, 6, 2),
    "revision": "00",
}
# Métodos de evaluación de la eficacia, en el orden de la planilla.
METODOS: tuple[tuple[str, str], ...] = (
    ("escrita", "Evaluación escrita"),
    ("oral", "Evaluación oral"),
    ("desempeno", "Evaluación de desempeño"),
    ("auditorias", "Resultado de auditorías Internas/externas"),
    ("cliente", "Satisfacción del Cliente"),
    ("otros", "Otros"),
)
SI_NO: tuple[str, ...] = ("SI", "NO")
FILAS_ASISTENTES = 17  # renglones de la planilla Word
CAMPOS_TEXTO: tuple[str, ...] = ("lugar", "duracion", "disertantes", "tema", "material", "nuevas_acciones_detalle")
_LARGOS = {"lugar": 255, "duracion": 60, "disertantes": 255}
CAMPO_LABELS: dict[str, str] = {
    "numero": "N° capacitación",
    "fecha": "Fecha",
    "lugar": "Lugar",
    "duracion": "Duración",
    "disertantes": "Disertante/es",
    "tema": "Tema",
    "material": "Material que se entrega",
    "metodos": "Método de evaluación de la eficacia",
    "asistentes": "Asistentes",
    "eficaz": "¿Fue eficaz la capacitación realizada?",
    "nuevas_acciones": "¿Se deben realizar nuevas acciones?",
    "nuevas_acciones_detalle": "Nuevas acciones",
    "alta": "Alta",
    "baja": "Baja",
}


def metodos(c: Capacitacion | None) -> dict[str, dict[str, Any]]:
    if c is None:
        return {}
    try:
        data = json.loads(c.metodos or "{}")
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def asistentes(c: Capacitacion | None) -> list[dict[str, Any]]:
    if c is None:
        return []
    try:
        data = json.loads(c.asistentes or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def empleados() -> list[EmpleadoPersonal]:
    return list(
        db.session.scalars(
            select(EmpleadoPersonal)
            .where(EmpleadoPersonal.estado == "activo")
            .order_by(EmpleadoPersonal.apellido, EmpleadoPersonal.nombre)
        )
    )


def labels_context() -> dict[str, Any]:
    return {
        "reg": REGISTRO, "metodos_op": METODOS, "si_no": SI_NO, "cp_campo_labels": CAMPO_LABELS, "fecha_local": fecha_local,
        "fecha_dmy": fecha_dmy, "metodos": metodos, "asistentes": asistentes, "filas_asistentes": FILAS_ASISTENTES,
    }


def listar() -> list[Capacitacion]:
    return list(
        db.session.scalars(
            select(Capacitacion).where(Capacitacion.activo.is_(True)).order_by(Capacitacion.numero.desc())
        )
    )


def get(capacitacion_id: int) -> Capacitacion | None:
    c = db.session.get(Capacitacion, int(capacitacion_id))
    return c if c is not None and c.activo else None


def cambios(c: Capacitacion, limit: int = 100) -> list[CapacitacionCambio]:
    return list(
        db.session.scalars(
            select(CapacitacionCambio)
            .where(CapacitacionCambio.capacitacion_id == c.id)
            .order_by(CapacitacionCambio.created_at.desc(), CapacitacionCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(c: Capacitacion, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        CapacitacionCambio(
            capacitacion_id=c.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes in (None, "") else str(antes),
            despues=None if despues in (None, "") else str(despues),
        )
    )


def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode()
    return re.sub(r"[\s,]+", " ", x).strip().lower()


def _legajos() -> dict[str, int]:
    """«apellido nombre» y «nombre apellido» normalizados → id del legajo activo."""
    out: dict[str, int] = {}
    for emp in empleados():
        out.setdefault(_norm(f"{emp.apellido} {emp.nombre}"), emp.id)
        out.setdefault(_norm(f"{emp.nombre} {emp.apellido}"), emp.id)
    return out


def _corto(val: Any, largo: int = 255) -> str:
    return re.sub(r"\s+", " ", str(val or "")).strip()[:largo]


def _metodos(data: Any) -> str:
    if hasattr(data, "getlist"):  # formulario: m_<clave>, m_<clave>_detalle/_responsable/_plazo
        crudos = {
            k: {"marcado": bool(data.get(f"m_{k}")), **{x: data.get(f"m_{k}_{x}") for x in ("detalle", "responsable", "plazo")}}
            for k, _ in METODOS
        }
    else:
        crudos = data.get("metodos") or {}
    out: dict[str, dict[str, Any]] = {}
    for k, _ in METODOS:
        cr = crudos.get(k) or {}
        fila = {"marcado": bool(cr.get("marcado")), **{x: _corto(cr.get(x)) for x in ("detalle", "responsable", "plazo")}}
        if fila["marcado"] or any(fila[x] for x in ("detalle", "responsable", "plazo")):
            out[k] = fila
    return json.dumps(out, ensure_ascii=False)


def _asistentes(data: Any) -> str:
    if hasattr(data, "getlist"):  # formulario: as_nombre_<i>, as_sector_<i>
        crudas = [
            {"nombre": data.get(f"as_nombre_{i}"), "sector": data.get(f"as_sector_{i}")}
            for i in range(int(data.get("as_filas") or 0))
        ]
    else:
        crudas = list(data.get("asistentes") or [])
    legajos = _legajos()
    out: list[dict[str, Any]] = []
    for cruda in crudas:
        fila: dict[str, Any] = {"nombre": _corto(cruda.get("nombre")), "sector": _corto(cruda.get("sector"))}
        if not fila["nombre"] and not fila["sector"]:
            continue
        emp_id = legajos.get(_norm(fila["nombre"]))
        if emp_id:
            fila["empleado_id"] = emp_id
        out.append(fila)
    return json.dumps(out, ensure_ascii=False)


def _limpio(data: Any) -> tuple[dict[str, Any], list[str]]:
    v: dict[str, Any] = {}
    errores: list[str] = []
    for k in CAMPOS_TEXTO:
        val = str(data.get(k) or "").strip()
        v[k] = _corto(val, _LARGOS[k]) if k in _LARGOS else val
    try:
        v["fecha"] = parse_fecha(data.get("fecha"))
    except ValueError:
        errores.append("Fecha: fecha inválida, usá dd/mm/aaaa.")
        v["fecha"] = None
    for k in ("eficaz", "nuevas_acciones"):
        val = _norm(str(data.get(k) or "")).upper()
        v[k] = val if val in SI_NO else ""
    v["metodos"] = _metodos(data)
    v["asistentes"] = _asistentes(data)
    if not v["tema"]:
        errores.append("El tema es obligatorio.")
    return v, errores


def _fmt(campo: str, val: Any) -> Any:
    if not val:
        return val
    if campo == "fecha":
        return fecha_dmy(val)
    if campo == "metodos":
        nombres = dict(METODOS)
        return "\n".join(
            " · ".join(x for x in (("☒ " if m["marcado"] else "☐ ") + nombres.get(k, k), m.get("detalle"), m.get("responsable"), m.get("plazo")) if x)
            for k, m in json.loads(val).items()
        ) or None
    if campo == "asistentes":
        return "\n".join(f"{a.get('nombre') or '—'} · {a.get('sector') or '—'}" for a in json.loads(val)) or None
    return val


def guardar(c: Capacitacion, data: Any, user_id: int | None) -> list[str]:
    v, errores = _limpio(data)
    if errores:
        return errores
    for campo, nuevo in v.items():
        antes = getattr(c, campo)
        if campo in ("metodos", "asistentes") and json.loads(antes or "null") == json.loads(nuevo):
            continue
        if (antes or None) == (nuevo or None):
            continue
        setattr(c, campo, nuevo)
        _log(c, user_id, campo, _fmt(campo, antes), _fmt(campo, nuevo))
    return []


def crear(data: Any, user_id: int | None) -> tuple[Capacitacion | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    numero = (db.session.scalar(select(func.max(Capacitacion.numero))) or 0) + 1
    c = Capacitacion(numero=numero, **v)
    db.session.add(c)
    db.session.flush()
    _log(c, user_id, "alta", None, f"N° {numero}: {c.tema}")
    return c, []


def baja(c: Capacitacion, user_id: int | None) -> None:
    c.activo = False
    _log(c, user_id, "baja", f"N° {c.numero}: {c.tema}", None)
