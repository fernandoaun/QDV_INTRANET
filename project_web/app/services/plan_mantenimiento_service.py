"""Plan de mantenimiento anual (registro SGI QDV-RG-PO-01_01), armado con los datos del módulo Mantenimiento.

No guarda nada propio: cada fila es un plan activo de Mantenimiento y cada mes muestra las órdenes de
trabajo de ese plan y, donde no hay orden, las fechas que salen de la próxima fecha y la frecuencia.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import MaintenancePlan
from app.services import mantenimiento_service as ms

REGISTRO = {"codigo": "QDV-RG-PO-01_01", "titulo": "PLAN DE MANTENIMIENTO", "procedimiento": "PO-01"}

MESES_CORTOS = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
_MESES_PERIODO = {"mensual": 1, "trimestral": 3, "semestral": 6, "anual": 12}

# Estado de una fecha del plan → (etiqueta, clase de color).
ESTADOS_MARCA: dict[str, tuple[str, str]] = {
    "hecho": ("Realizado", "pm-hecho"),
    "vencido": ("Vencido", "pm-vencido"),
    "programado": ("Programado", "pm-programado"),
    "previsto": ("Previsto por frecuencia", "pm-previsto"),
}


@dataclass
class Marca:
    fecha: date
    estado: str
    order_id: int | None = None


@dataclass
class FilaPlan:
    plan: MaintenancePlan
    activo: str
    ubicacion: str
    tipo: str
    frecuencia: str
    responsable: str
    proxima: date | None
    meses: list[list[Marca]] = field(default_factory=lambda: [[] for _ in range(12)])
    n_ordenes: int = 0


def _fecha(raw: str | None) -> date | None:
    try:
        return date.fromisoformat((raw or "")[:10])
    except ValueError:
        return None


def _sumar_meses(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    ultimo = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, ultimo))


def frecuencia_label(plan: MaintenancePlan) -> str:
    partes = []
    if plan.frecuencia_periodo:
        partes.append(ms.FRECUENCIA_PERIODOS.get(plan.frecuencia_periodo, plan.frecuencia_periodo))
    if plan.frecuencia_dias:
        partes.append(f"Cada {plan.frecuencia_dias} días")
    if plan.frecuencia_horas_uso:
        partes.append(f"Cada {plan.frecuencia_horas_uso:g} h de uso")
    return " · ".join(partes)


def _siguiente(d: date, plan: MaintenancePlan) -> date | None:
    if plan.frecuencia_dias and plan.frecuencia_dias > 0:
        return d + timedelta(days=int(plan.frecuencia_dias))
    meses = _MESES_PERIODO.get(plan.frecuencia_periodo or "")
    return _sumar_meses(d, meses) if meses else None


def _previstas(plan: MaintenancePlan, anio: int) -> list[date]:
    """Fechas del año que salen de la próxima fecha del plan y su frecuencia."""
    d = _fecha(plan.proxima_fecha)
    out: list[date] = []
    while d is not None and d.year <= anio and len(out) < 400:
        if d.year == anio:
            out.append(d)
        d = _siguiente(d, plan)
    return out


def plan_anual(anio: int, today: date | None = None) -> list[FilaPlan]:
    today = today or date.today()
    planes = db.session.scalars(
        select(MaintenancePlan)
        .where(MaintenancePlan.activo.is_(True))
        .options(selectinload(MaintenancePlan.equipo), selectinload(MaintenancePlan.component), selectinload(MaintenancePlan.orders))
    ).all()
    filas: list[FilaPlan] = []
    for p in planes:
        eq = p.equipo
        activo = eq.nombre_equipo if eq is not None else "—"
        if p.component is not None:
            activo = f"{activo} · {p.component.nombre}"
        fila = FilaPlan(
            plan=p,
            activo=activo,
            ubicacion=(eq.area_sector if eq is not None else "") or "",
            tipo=ms.TIPOS_MANTENIMIENTO.get(p.tipo_mantenimiento, p.tipo_mantenimiento or ""),
            frecuencia=frecuencia_label(p),
            responsable=p.responsable or "",
            proxima=_fecha(p.proxima_fecha),
        )
        meses_con_orden: set[int] = set()
        for o in p.orders:
            if o.estado == "cancelado":
                continue
            fila.n_ordenes += 1
            f = _fecha(o.fecha_programada)
            if f is None or f.year != anio:
                continue
            if o.estado == "finalizado":
                estado = "hecho"
            elif f < today:
                estado = "vencido"
            else:
                estado = "programado"
            fila.meses[f.month - 1].append(Marca(f, estado, int(o.id)))
            meses_con_orden.add(f.month)
        for f in _previstas(p, anio):
            if f.month not in meses_con_orden:
                fila.meses[f.month - 1].append(Marca(f, "vencido" if f < today else "previsto"))
        for m in fila.meses:
            m.sort(key=lambda x: x.fecha)
        filas.append(fila)
    filas.sort(key=lambda r: (r.ubicacion.lower(), r.activo.lower(), r.plan.nombre.lower()))
    return filas


def labels_context() -> dict[str, Any]:
    return {"reg_pm": REGISTRO, "meses_cortos": MESES_CORTOS, "estados_marca": ESTADOS_MARCA}
