"""Registro de NC, PNC y OM (QDV-RG-PG-08_01): un reporte por desvío, editable, con historial.

El listado de reportes, con su resumen por tipo y estado, es el Seguimiento de PNC, NC y OM (QDV-RG-PG-08_02).
Las acciones con responsable pasan al Plan de acción (QDV-RG-PG-02_03).
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import Desvio, DesvioCambio
from app.services import plan_accion_service as plan
from app.services.fichas_proceso_service import fecha_local, items
from app.services.plan_accion_service import fecha_dmy, parse_fecha
from app.utils.datetime_operacion import operacion_zoneinfo

REGISTRO = {
    "codigo": "QDV-RG-PG-08_01",
    "titulo": "Registro de No conformidades, PNC y OM",
    "revision": "00",
    "aprobacion": date(2026, 9, 29),
}
SEGUIMIENTO = {
    "codigo": "QDV-RG-PG-08_02",
    "titulo": "Seguimiento de No Conformidades, PNC, y OM.",
    "revision": "00",
    "aprobacion": date(2026, 9, 24),
}
# Clasificación del reporte → tipo en el seguimiento y tipo de hallazgo en el plan de acción.
CLASIFICACIONES: dict[str, tuple[str, str]] = {
    "No conformidad": ("NC", "No Conformidad"),
    "Producto N.C.": ("PNC", "No Conformidad"),
    "Oportunidad de mejora": ("OM", "Oportunidad de Mejora"),
}
TIPOS: tuple[str, ...] = ("PNC", "NC", "OM")
FUENTES: tuple[str, ...] = (
    "Reclamo del cliente", "Reclamo parte interesada", "Auditoría interna / externa",
    "Incumplimiento de normas internas", "Otros", "Producto / servicio no conforme",
)
ENCUADRES: tuple[str, ...] = (
    "Prestación del servicio", "Gestión de proveedores / compras", "Infraestructura y ambiente de trabajo",
    "Comunicaciones internas y externas", "Calibración de equipos",
    "Control de documentos y registros", "Objetivos, metas y programas", "Competencia y toma de conciencia",
    "Requisitos del cliente, legales, otros", "Satisfacción del cliente",
    "Revisión por la dirección", "Planes de emergencia", "Gestión de incidentes", "Aspectos / impactos ambientales",
    "Peligros / riesgos",
    "Auditoría interna", "Gestión de servicio / PNC", "Medición y seguimiento", "Gestión de residuos", "Otros",
)
ESTADOS: tuple[str, ...] = ("Abierta", "En proceso de cierre", "Cerrada")
SI_NO: tuple[str, ...] = ("Sí", "No")
# Tablas de acciones: clave → (título en el formulario, tipo de acción en el plan).
TABLAS: dict[str, tuple[str, str]] = {
    "acciones_inmediatas": ("Acciones inmediatas (AI) – Responsables", "Acción corrección (inmediata)"),
    "correcciones": ("Corrección (C) – Responsables", "Acción corrección (inmediata)"),
    "acciones_correctivas": ("Acciones correctivas (AC) – Responsables", "Acción correctiva"),
}
FILAS_MIN: dict[str, int] = {"acciones_inmediatas": 1, "correcciones": 2, "acciones_correctivas": 2}
CAMPOS_FILA: tuple[str, ...] = ("detalle", "responsable", "fecha")
CAMPOS_TEXTO: tuple[str, ...] = (
    "clasificacion", "descripcion", "emisor", "requisito", "causa_raiz", "evidencia", "verificador", "implementadas",
    "eficaces", "estado",
)
CAMPOS_FECHA: tuple[str, ...] = ("fecha", "fecha_implementacion", "fecha_eficacia", "fecha_cierre")
LISTAS: tuple[str, ...] = ("fuentes", "encuadre", "cierre_responsables")
_LARGOS = {"clasificacion": 30, "emisor": 255, "verificador": 255, "implementadas": 2, "eficaces": 2, "estado": 30}
CAMPO_LABELS: dict[str, str] = {
    "numero": "Reporte N°",
    "fecha": "Fecha",
    "clasificacion": "Clasificación",
    "fuentes": "Fuente de origen",
    "descripcion": "Descripción del hallazgo",
    "emisor": "Emisor",
    "encuadre": "Encuadramiento en el SGC",
    "requisito": "Requisito de referencia",
    "causa_raiz": "Análisis de causa raíz",
    "acciones_inmediatas": "Acciones inmediatas (AI)",
    "correcciones": "Corrección (C)",
    "acciones_correctivas": "Acciones correctivas (AC)",
    "evidencia": "Evidencia que se adjunta",
    "verificador": "Responsable de la verificación de la eficacia",
    "implementadas": "¿Las acciones propuestas fueron implementadas?",
    "fecha_implementacion": "Fecha de implementación",
    "eficaces": "¿Fueron eficaces?",
    "fecha_eficacia": "Fecha de verificación de la eficacia",
    "cierre_responsables": "Responsables al cierre del reporte",
    "fecha_cierre": "Fecha de cierre",
    "estado": "Estado",
    "alta": "Alta",
    "baja": "Baja",
}


def tipo(d: Desvio) -> str:
    return CLASIFICACIONES.get(d.clasificacion, ("", ""))[0]


def filas(d: Desvio | None, tabla: str) -> list[dict[str, Any]]:
    if d is None:
        return []
    try:
        data = json.loads(getattr(d, tabla) or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)]


def plan_numeros(d: Desvio | None) -> dict[int, int]:
    return plan.numeros([f["plan_accion_id"] for t in TABLAS for f in filas(d, t) if f.get("plan_accion_id")])


def labels_context() -> dict[str, Any]:
    return {
        "reg": REGISTRO, "seg": SEGUIMIENTO, "clasificaciones": tuple(CLASIFICACIONES), "fuentes_op": FUENTES,
        "encuadres_op": ENCUADRES, "estados": ESTADOS, "si_no": SI_NO, "tablas": TABLAS, "filas_min": FILAS_MIN,
        "dv_campo_labels": CAMPO_LABELS, "fecha_local": fecha_local, "fecha_dmy": fecha_dmy, "items": items,
        "filas": filas, "tipo": tipo, "plan_numeros": plan_numeros,
    }


def listar() -> list[Desvio]:
    return list(db.session.scalars(select(Desvio).where(Desvio.activo.is_(True)).order_by(Desvio.numero.desc())))


def get(desvio_id: int) -> Desvio | None:
    d = db.session.get(Desvio, int(desvio_id))
    return d if d is not None and d.activo else None


def resumen(desvios: list[Desvio]) -> dict[str, Any]:
    """Resumen consolidado del seguimiento: por tipo y estado, totales y tasa de cierre."""
    por_tipo = {t: {e: 0 for e in ESTADOS} | {"total": 0} for t in TIPOS}
    for d in desvios:
        t = tipo(d)
        if t in por_tipo:
            por_tipo[t]["total"] += 1
            if d.estado in ESTADOS:
                por_tipo[t][d.estado] += 1
    total = {e: sum(v[e] for v in por_tipo.values()) for e in (*ESTADOS, "total")}
    return {
        "por_tipo": por_tipo,
        "total": total,
        "tasa_cierre": round(100 * total["Cerrada"] / total["total"]) if total["total"] else 0,
        "pendientes": total["total"] - total["Cerrada"],
    }


def ultima_actualizacion() -> date | None:
    ult = db.session.scalar(select(func.max(DesvioCambio.created_at)))
    return ult.astimezone(operacion_zoneinfo()).date() if ult is not None else None


def cambios(d: Desvio, limit: int = 100) -> list[DesvioCambio]:
    return list(
        db.session.scalars(
            select(DesvioCambio)
            .where(DesvioCambio.desvio_id == d.id)
            .order_by(DesvioCambio.created_at.desc(), DesvioCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(d: Desvio, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        DesvioCambio(
            desvio_id=d.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes in (None, "") else str(antes),
            despues=None if despues in (None, "") else str(despues),
        )
    )


def _opcion(valor: str, opciones: tuple[str, ...]) -> str:
    return next((o for o in opciones if o.lower() == valor.lower()), valor)


def _lista(data: Any, k: str) -> list[str]:
    getlist = getattr(data, "getlist", None)
    if k == "cierre_responsables":
        if getlist:
            n = int(data.get("cierre_filas") or 0)
            return [x for x in (re.sub(r"\s+", " ", str(data.get(f"cierre_{i}") or "")).strip() for i in range(n)) if x]
        return items(data.get(k) or "")
    marcados = getlist(k) if getlist else (data.get(k) or [])
    if isinstance(marcados, str):
        marcados = items(marcados)
    opciones = FUENTES if k == "fuentes" else ENCUADRES
    return [o for o in opciones if o in marcados]


def _tabla(data: Any, tabla: str, errores: list[str]) -> list[dict[str, Any]]:
    if hasattr(data, "getlist"):
        crudas = [
            {**{k: data.get(f"{tabla}_{k}_{i}") for k in CAMPOS_FILA}, "plan_accion_id": data.get(f"{tabla}_plan_{i}")}
            for i in range(int(data.get(f"{tabla}_filas") or 0))
        ]
    else:
        crudas = list(data.get(tabla) or [])
    out = []
    for i, cruda in enumerate(crudas):
        fila: dict[str, Any] = {k: re.sub(r"\s+", " ", str(cruda.get(k) or "")).strip()[:500] for k in CAMPOS_FILA}
        if not any(fila.values()):
            continue
        if fila["fecha"]:
            try:
                fila["fecha"] = fecha_dmy(parse_fecha(fila["fecha"]))
            except ValueError:
                errores.append(f"{CAMPO_LABELS[tabla]}, renglón {i + 1}: fecha inválida, usá dd/mm/aaaa.")
        if str(cruda.get("plan_accion_id") or "").isdigit():
            fila["plan_accion_id"] = int(cruda["plan_accion_id"])
        out.append(fila)
    return out


def _limpio(data: Any) -> tuple[dict[str, Any], list[str]]:
    v: dict[str, Any] = {}
    errores: list[str] = []
    for k in CAMPOS_TEXTO:
        val = str(data.get(k) or "").strip()
        if k in _LARGOS:
            val = re.sub(r"\s+", " ", val)[: _LARGOS[k]]
        v[k] = val
    v["clasificacion"] = _opcion(v["clasificacion"], tuple(CLASIFICACIONES)) if v["clasificacion"] else ""
    v["estado"] = _opcion(v["estado"], ESTADOS) if v["estado"] else "Abierta"
    for k in ("implementadas", "eficaces"):
        v[k] = _opcion(v[k], SI_NO) if v[k] else ""
        if v[k] and v[k] not in SI_NO:
            errores.append(f"{CAMPO_LABELS[k]}: respondé Sí o No.")
    if v["clasificacion"] and v["clasificacion"] not in CLASIFICACIONES:
        errores.append("La clasificación es No conformidad, Producto N.C. u Oportunidad de mejora.")
    if v["estado"] not in ESTADOS:
        errores.append("El estado es Abierta, En proceso de cierre o Cerrada.")
    for k in CAMPOS_FECHA:
        try:
            v[k] = parse_fecha(data.get(k))
        except ValueError:
            errores.append(f"{CAMPO_LABELS[k]}: fecha inválida, usá dd/mm/aaaa.")
            v[k] = None
    for k in LISTAS:
        v[k] = "\n".join(_lista(data, k))
    for t in TABLAS:
        v[t] = _tabla(data, t, errores)
    if not v["descripcion"]:
        errores.append("La descripción del hallazgo es obligatoria.")
    return v, errores


def _fmt(campo: str, val: Any) -> Any:
    if not val:
        return val
    if campo in CAMPOS_FECHA:
        return fecha_dmy(val)
    if campo in TABLAS:
        return "\n".join(" · ".join(f.get(k, "") or "—" for k in CAMPOS_FILA) for f in json.loads(val)) or None
    return val


def sincronizar_plan(d: Desvio, user_id: int | None) -> int:
    """Las acciones del reporte con responsable son acciones del Plan de acción. Devuelve cuántas creó."""
    hallazgo = CLASIFICACIONES.get(d.clasificacion, ("", "Otros"))[1]
    base = {
        "origen": "Registro de NC, PNC y OM", "tipo_hallazgo": hallazgo, "fecha_deteccion": d.fecha,
        "requisito": f"{REGISTRO['codigo']} Reporte N° {d.numero}",
        "causa_raiz": "Aplica" if d.causa_raiz else "", "causa_raiz_descripcion": d.causa_raiz,
    }
    creadas = 0
    for t, (_, tipo_accion) in TABLAS.items():
        fs = filas(d, t)
        creadas += plan.sincronizar_filas(fs, {**base, "tipo_accion": tipo_accion}, user_id, texto="detalle")
        setattr(d, t, json.dumps(fs, ensure_ascii=False))
    return creadas


def guardar(d: Desvio, data: Any, user_id: int | None) -> list[str]:
    v, errores = _limpio(data)
    if errores:
        return errores
    for t in TABLAS:
        plan.conservar_ids(filas(d, t), v[t], texto="detalle")
        v[t] = json.dumps(v[t], ensure_ascii=False)
    for campo, nuevo in v.items():
        antes = getattr(d, campo)
        if campo in TABLAS and json.loads(antes or "[]") == json.loads(nuevo):
            continue
        if (antes or None) == (nuevo or None):
            continue
        setattr(d, campo, nuevo)
        _log(d, user_id, campo, _fmt(campo, antes), _fmt(campo, nuevo))
    return []


def crear(data: Any, user_id: int | None) -> tuple[Desvio | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    for t in TABLAS:
        v[t] = json.dumps(v[t], ensure_ascii=False)
    numero = (db.session.scalar(select(func.max(Desvio.numero))) or 0) + 1
    d = Desvio(numero=numero, **v)
    db.session.add(d)
    db.session.flush()
    _log(d, user_id, "alta", None, f"N° {numero}: {d.descripcion[:200]}")
    return d, []


def baja(d: Desvio, user_id: int | None) -> None:
    d.activo = False
    _log(d, user_id, "baja", f"N° {d.numero}: {d.descripcion[:200]}", None)
