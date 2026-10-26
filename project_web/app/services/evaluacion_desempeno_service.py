"""Evaluación de desempeño (registro SGI QDV-RG-PG-05_04): una hoja por evaluación, editable, con historial."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import EmpleadoPersonal, EvaluacionDesempeno, EvaluacionDesempenoCambio
from app.services.fichas_proceso_service import fecha_local, items
from app.services.plan_accion_service import fecha_dmy, parse_fecha

REGISTRO = {
    "codigo": "QDV-RG-PG-05_04",
    "titulo": "EVALUACIÓN DE DESEMPEÑO",
    "fecha_vigencia": date(2026, 6, 24),
    "revision": "00",
}
# Áreas de desempeño y sus ítems, en el orden de la planilla. Los ítems se numeran 1..18 en ese orden.
AREAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ORIENTACIÓN DE RESULTADOS", (
        "Termina su trabajo oportunamente",
        "Cumple con las tareas que se le encomienda",
        "Planifica sus actividades",
        "Hace uso de indicadores",
        "Se preocupa por alcanzar las metas",
        "Establece los tiempos de realización de los trabajos y controla su cumplimiento.",
    )),
    ("CALIDAD", (
        "No comete errores en el trabajo",
        "Hace uso racional de los recursos",
        "No requiere de supervisión frecuente",
        "Se muestra profesional en el trabajo",
    )),
    ("RELACIONES INTERPERSONALES", (
        "Se muestra cortés con los clientes, proveedores y/o sus compañeros",
    )),
    ("INICIATIVA", (
        "Muestra nuevas ideas para mejorar los procesos",
        "Se muestra predispuesto al cambio",
        "Se anticipa a las dificultades",
        "Tiene gran capacidad para resolver problemas",
    )),
    ("TRABAJO EN EQUIPO", (
        "Evita los conflictos dentro del equipo",
        "Muestra aptitud para integrarse al equipo",
        "Se identifica fácilmente con los objetivos del equipo",
    )),
)
N_ITEMS = sum(len(its) for _, its in AREAS)
ESCALA: tuple[tuple[int, str, str], ...] = (
    (1, "DEFICIENTE", "Inferior, rendimiento laboral no aceptable."),
    (2, "BAJO", "Inferior al promedio, rendimiento laboral regular."),
    (3, "BUENO", "Promedio, rendimiento laboral bueno."),
    (4, "ALTO", "Superior al promedio, rendimiento laboral muy bueno."),
    (5, "EXCELENTE", "Superior, rendimiento laboral excelente."),
)
# Análisis de resultados: rango de puntaje total → nivel.
NIVELES: tuple[tuple[int, int, str], ...] = (
    (18, 35, "Deficiente"),
    (36, 53, "Bajo"),
    (54, 71, "Bueno"),
    (72, 89, "Alto"),
    (90, 90, "Excelente"),
)
CAMPOS_TEXTO: tuple[str, ...] = (
    "sector", "puesto", "evaluado", "periodo", "evaluador", "comentarios_evaluador", "comentarios_evaluado",
    "observaciones", "objetivos",
)
_LARGOS = {"sector": 128, "puesto": 128, "evaluado": 255, "periodo": 80, "evaluador": 255}
CAMPO_LABELS: dict[str, str] = {
    "numero": "N° evaluación",
    "sector": "Sector",
    "puesto": "Puesto",
    "evaluado": "Evaluado",
    "periodo": "Período evaluado",
    "evaluador": "Evaluador",
    "fecha": "Fecha de evaluación",
    "puntajes": "Puntajes",
    "comentarios_evaluador": "Comentarios del evaluador",
    "comentarios_evaluado": "Comentarios del evaluado",
    "observaciones": "Observaciones (concientización, formación, competencia / oportunidades de mejora)",
    "objetivos": "Objetivos para el próximo período",
    "alta": "Alta",
    "baja": "Baja",
}
FILAS_LISTAS = 4  # renglones de observaciones y de objetivos en el formulario


def areas_numeradas() -> list[tuple[str, list[tuple[int, str]]]]:
    out, n = [], 0
    for area, its in AREAS:
        fila = []
        for it in its:
            n += 1
            fila.append((n, it))
        out.append((area, fila))
    return out


def puntajes(e: EvaluacionDesempeno | None) -> dict[int, int]:
    if e is None:
        return {}
    try:
        data = json.loads(e.puntajes or "{}")
    except ValueError:
        return {}
    return {int(k): int(v) for k, v in data.items() if str(k).isdigit() and str(v).isdigit()}


def total(e: EvaluacionDesempeno | None) -> int | None:
    """Puntaje total; None mientras falte puntuar algún ítem."""
    p = puntajes(e)
    return sum(p.values()) if len(p) == N_ITEMS else None


def nivel(e: EvaluacionDesempeno | None) -> str:
    t = total(e)
    if t is None:
        return ""
    return next((n for lo, hi, n in NIVELES if lo <= t <= hi), "")


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
        "reg": REGISTRO, "areas": areas_numeradas(), "escala": ESCALA, "niveles": NIVELES, "ed_campo_labels": CAMPO_LABELS,
        "fecha_local": fecha_local, "fecha_dmy": fecha_dmy, "items": items, "puntajes": puntajes, "total": total,
        "nivel": nivel, "filas_listas": FILAS_LISTAS, "n_items": N_ITEMS,
    }


def listar() -> list[EvaluacionDesempeno]:
    return list(
        db.session.scalars(
            select(EvaluacionDesempeno)
            .where(EvaluacionDesempeno.activo.is_(True))
            .order_by(EvaluacionDesempeno.numero.desc())
        )
    )


def get(evaluacion_id: int) -> EvaluacionDesempeno | None:
    e = db.session.get(EvaluacionDesempeno, int(evaluacion_id))
    return e if e is not None and e.activo else None


def cambios(e: EvaluacionDesempeno, limit: int = 100) -> list[EvaluacionDesempenoCambio]:
    return list(
        db.session.scalars(
            select(EvaluacionDesempenoCambio)
            .where(EvaluacionDesempenoCambio.evaluacion_id == e.id)
            .order_by(EvaluacionDesempenoCambio.created_at.desc(), EvaluacionDesempenoCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(e: EvaluacionDesempeno, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        EvaluacionDesempenoCambio(
            evaluacion_id=e.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes in (None, "") else str(antes),
            despues=None if despues in (None, "") else str(despues),
        )
    )


def _empleado_id(nombre: str) -> int | None:
    """Legajo cuyo «Apellido, Nombre» (o «Nombre Apellido») coincide con el evaluado."""
    def norm(x: str) -> str:
        x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode()
        return re.sub(r"[\s,]+", " ", x).strip().lower()

    clave = norm(nombre)
    if not clave:
        return None
    for emp in empleados():
        if clave in (norm(f"{emp.apellido} {emp.nombre}"), norm(f"{emp.nombre} {emp.apellido}")):
            return emp.id
    return None


def _limpio(data: Any) -> tuple[dict[str, Any], list[str]]:
    v: dict[str, Any] = {}
    errores: list[str] = []
    for k in CAMPOS_TEXTO:
        val = str(data.get(k) or "").strip()
        if k in _LARGOS:
            val = re.sub(r"\s+", " ", val)[: _LARGOS[k]]
        elif k in ("observaciones", "objetivos"):
            val = "\n".join(items(val))
        v[k] = val
    if hasattr(data, "getlist"):  # formulario: renglones obs_<i> / obj_<i>
        for k, pref in (("observaciones", "obs"), ("objetivos", "obj")):
            n = int(data.get(f"{pref}_filas") or 0)
            v[k] = "\n".join(x for x in (re.sub(r"\s+", " ", str(data.get(f"{pref}_{i}") or "")).strip() for i in range(n)) if x)
    try:
        v["fecha"] = parse_fecha(data.get("fecha"))
    except ValueError:
        errores.append("Fecha de evaluación: fecha inválida, usá dd/mm/aaaa.")
        v["fecha"] = None
    crudos = data.get("puntajes") if isinstance(data.get("puntajes"), dict) else {
        i: data.get(f"p_{i}") for i in range(1, N_ITEMS + 1)
    }
    p: dict[str, int] = {}
    for i in range(1, N_ITEMS + 1):
        raw = str(crudos.get(i) or crudos.get(str(i)) or "").strip()
        if not raw:
            continue
        if raw not in ("1", "2", "3", "4", "5"):
            errores.append(f"Ítem {i}: el puntaje va de 1 a 5.")
            continue
        p[str(i)] = int(raw)
    v["puntajes"] = json.dumps(dict(sorted(p.items(), key=lambda x: int(x[0]))))
    if not v["evaluado"]:
        errores.append("El evaluado es obligatorio.")
    v["empleado_id"] = _empleado_id(v["evaluado"])
    return v, errores


def _fmt(campo: str, val: Any) -> Any:
    if not val:
        return val
    if campo == "fecha":
        return fecha_dmy(val)
    if campo == "puntajes":
        p = json.loads(val)
        return ", ".join(f"{k}: {n}" for k, n in p.items()) + f" (total {sum(p.values())})" if p else None
    return val


def guardar(e: EvaluacionDesempeno, data: Any, user_id: int | None) -> list[str]:
    v, errores = _limpio(data)
    if errores:
        return errores
    for campo, nuevo in v.items():
        antes = getattr(e, campo)
        if campo == "puntajes" and json.loads(antes or "{}") == json.loads(nuevo):
            continue
        if (antes or None) == (nuevo or None):
            continue
        setattr(e, campo, nuevo)
        if campo != "empleado_id":
            _log(e, user_id, campo, _fmt(campo, antes), _fmt(campo, nuevo))
    return []


def crear(data: Any, user_id: int | None) -> tuple[EvaluacionDesempeno | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    numero = (db.session.scalar(select(func.max(EvaluacionDesempeno.numero))) or 0) + 1
    e = EvaluacionDesempeno(numero=numero, **v)
    db.session.add(e)
    db.session.flush()
    _log(e, user_id, "alta", None, f"N° {numero}: {e.evaluado}")
    return e, []


def baja(e: EvaluacionDesempeno, user_id: int | None) -> None:
    e.activo = False
    _log(e, user_id, "baja", f"N° {e.numero}: {e.evaluado}", None)
