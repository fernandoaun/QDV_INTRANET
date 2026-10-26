"""Minuta de reunión (registro SGI QDV-RG-PG-04_01): una hoja por reunión, editable, con historial."""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import MinutaReunion, MinutaReunionCambio
from app.services import plan_accion_service as plan
from app.services.fichas_proceso_service import fecha_local
from app.services.plan_accion_service import fecha_dmy, parse_fecha

REGISTRO = {
    "codigo": "QDV-RG-PG-04_01",
    "titulo": "MINUTA DE REUNIÓN",
    "fecha_vigencia": date(2026, 9, 8),
    "revision": "00",
}
ASISTENCIA: tuple[str, ...] = ("Presente", "Ausente")
# Tablas de la hoja: campos de cada renglón y renglones del formulario Word.
TABLAS: dict[str, tuple[str, ...]] = {
    "participantes": ("participante", "sector", "asistencia"),
    "acciones": ("accion", "responsable", "fecha"),
}
FILAS: dict[str, int] = {"participantes": 10, "acciones": 3}
CAMPOS_TEXTO: tuple[str, ...] = ("horario", "lugar", "motivo", "desarrollo")
_LARGOS = {"horario": 60, "lugar": 255}
CAMPO_LABELS: dict[str, str] = {
    "numero": "N° minuta",
    "fecha": "Fecha",
    "horario": "Horario",
    "lugar": "Lugar",
    "motivo": "Motivo de la reunión",
    "participantes": "Participantes",
    "desarrollo": "Desarrollo",
    "acciones": "Acciones / conclusiones",
    "alta": "Alta",
    "baja": "Baja",
}


def filas(m: MinutaReunion | None, tabla: str) -> list[dict[str, str]]:
    if m is None:
        return []
    try:
        data = json.loads(getattr(m, tabla) or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)]


def presentes(m: MinutaReunion) -> int:
    return sum(1 for p in filas(m, "participantes") if p.get("asistencia") == "Presente")


def labels_context() -> dict[str, Any]:
    return {
        "reg": REGISTRO, "asistencia_op": ASISTENCIA, "mr_campo_labels": CAMPO_LABELS, "fecha_local": fecha_local,
        "fecha_dmy": fecha_dmy, "filas": filas, "filas_min": FILAS, "presentes": presentes, "plan_numeros": plan_numeros,
    }


def listar() -> list[MinutaReunion]:
    return list(
        db.session.scalars(
            select(MinutaReunion).where(MinutaReunion.activo.is_(True)).order_by(MinutaReunion.numero.desc())
        )
    )


def get(minuta_id: int) -> MinutaReunion | None:
    m = db.session.get(MinutaReunion, int(minuta_id))
    return m if m is not None and m.activo else None


def cambios(m: MinutaReunion, limit: int = 100) -> list[MinutaReunionCambio]:
    return list(
        db.session.scalars(
            select(MinutaReunionCambio)
            .where(MinutaReunionCambio.minuta_id == m.id)
            .order_by(MinutaReunionCambio.created_at.desc(), MinutaReunionCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(m: MinutaReunion, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        MinutaReunionCambio(
            minuta_id=m.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes in (None, "") else str(antes),
            despues=None if despues in (None, "") else str(despues),
        )
    )


def _tabla(data: Any, tabla: str, errores: list[str]) -> str:
    """Renglones de la tabla desde el formulario (<tabla>_<campo>_<i>) o desde una lista; descarta los vacíos."""
    campos = TABLAS[tabla]
    if hasattr(data, "getlist"):
        crudas = [
            {**{k: data.get(f"{tabla}_{k}_{i}") for k in campos}, "plan_accion_id": data.get(f"{tabla}_plan_{i}")}
            for i in range(int(data.get(f"{tabla}_filas") or 0))
        ]
    else:
        crudas = list(data.get(tabla) or [])
    out: list[dict[str, str]] = []
    for i, cruda in enumerate(crudas):
        fila = {k: re.sub(r"\s+", " ", str(cruda.get(k) or "")).strip()[:255] for k in campos}
        if not any(fila.values()):
            continue
        if fila.get("asistencia"):
            fila["asistencia"] = next((a for a in ASISTENCIA if a.lower() == fila["asistencia"].lower()), fila["asistencia"])
        if fila.get("fecha"):
            try:
                fila["fecha"] = fecha_dmy(parse_fecha(fila["fecha"]))
            except ValueError:
                errores.append(f"{CAMPO_LABELS[tabla]}, renglón {i + 1}: fecha inválida, usá dd/mm/aaaa.")
        if str(cruda.get("plan_accion_id") or "").isdigit():
            fila["plan_accion_id"] = int(cruda["plan_accion_id"])
        out.append(fila)
    return json.dumps(out, ensure_ascii=False)


def _limpio(data: Any) -> tuple[dict[str, Any], list[str]]:
    v: dict[str, Any] = {}
    errores: list[str] = []
    for k in CAMPOS_TEXTO:
        val = str(data.get(k) or "").strip()
        v[k] = re.sub(r"\s+", " ", val)[: _LARGOS[k]] if k in _LARGOS else val
    try:
        v["fecha"] = parse_fecha(data.get("fecha"))
    except ValueError:
        errores.append("Fecha: fecha inválida, usá dd/mm/aaaa.")
        v["fecha"] = None
    for t in TABLAS:
        v[t] = _tabla(data, t, errores)
    if not v["motivo"]:
        errores.append("El motivo de la reunión es obligatorio.")
    return v, errores


def _fmt(campo: str, val: Any) -> Any:
    if not val:
        return val
    if campo == "fecha":
        return fecha_dmy(val)
    if campo in TABLAS:
        return "\n".join(" · ".join(f.get(k, "") or "—" for k in TABLAS[campo]) for f in json.loads(val)) or None
    return val


def sincronizar_plan(m: MinutaReunion, user_id: int | None) -> int:
    """Cada acción de la minuta con responsable es una acción del Plan de acción (QDV-RG-PG-02_03).

    Los renglones sin responsable son conclusiones y no pasan al plan. Devuelve cuántas acciones creó.
    """
    filas_ = filas(m, "acciones")
    base = {"origen": "Minuta de reunión", "fecha_deteccion": m.fecha, "requisito": f"{REGISTRO['codigo']} Minuta N° {m.numero}"}
    creadas = plan.sincronizar_filas(filas_, base, user_id)
    m.acciones = json.dumps(filas_, ensure_ascii=False)
    return creadas


def plan_numeros(m: MinutaReunion | None) -> dict[int, int]:
    """id de acción del plan → su N°, para los renglones de la minuta que ya están en el plan."""
    return plan.numeros([f["plan_accion_id"] for f in filas(m, "acciones") if f.get("plan_accion_id")])


def guardar(m: MinutaReunion, data: Any, user_id: int | None) -> list[str]:
    v, errores = _limpio(data)
    if errores:
        return errores
    nuevas = json.loads(v["acciones"])
    plan.conservar_ids(filas(m, "acciones"), nuevas)
    v["acciones"] = json.dumps(nuevas, ensure_ascii=False)
    for campo, nuevo in v.items():
        antes = getattr(m, campo)
        if campo in TABLAS and json.loads(antes or "[]") == json.loads(nuevo):
            continue
        if (antes or None) == (nuevo or None):
            continue
        setattr(m, campo, nuevo)
        _log(m, user_id, campo, _fmt(campo, antes), _fmt(campo, nuevo))
    return []


def crear(data: Any, user_id: int | None) -> tuple[MinutaReunion | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    numero = (db.session.scalar(select(func.max(MinutaReunion.numero))) or 0) + 1
    m = MinutaReunion(numero=numero, **v)
    db.session.add(m)
    db.session.flush()
    _log(m, user_id, "alta", None, f"N° {numero}: {m.motivo}")
    return m, []


def baja(m: MinutaReunion, user_id: int | None) -> None:
    m.activo = False
    _log(m, user_id, "baja", f"N° {m.numero}: {m.motivo}", None)
