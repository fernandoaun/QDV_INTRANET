"""
Indicadores operativos de hipoclorito a partir del stock declarado en cambio de turno
(`ShiftHandover.hypochlorite_stock_liters`) y cargas de camión en entregas (`Entrega`).

Para importar desde rutas u otros servicios usá `app.services.operational_informed_stock`
(la API pública y las validaciones de negocio); este archivo conserva la implementación.

Fuente única de verdad operativa (litros) para el Panel y para validar Entregas de hipoclorito:
- Stock instantáneo = último stock informado en turno recepcionado − suma de litros de entregas
  en estado «cargada» desde ese cierre (ver `get_instant_stock`).
- Las entregas «programada» comprometen litros contra ese mismo techo (ver
  `operational_liters_available_for_new_programada`).

No usar para este criterio el stock teórico por marca (`ingresos_stock` / `consumos_stock`);
ese ledger sigue existiendo solo para trazabilidad al registrar el consumo al marcar «Cargar».
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import Entrega, ShiftHandover
from app.services import shift_handover_service as sh
from app.utils.hipoclorito_producto import entrega_columna_es_hipoclorito_operativo_sql


def _finite_non_negative_stock(v: Any) -> bool:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and x >= 0.0


def _hipo_product_sql_match():
    """Entregas cuyo `producto` es hipoclorito operativo (cualquier alias; mismo criterio que backend/Panel)."""
    return entrega_columna_es_hipoclorito_operativo_sql(Entrega.producto)


def _list_received_handovers_with_valid_stock(limit: int = 80) -> list[ShiftHandover]:
    rows = list(
        db.session.scalars(
            select(ShiftHandover)
            .where(ShiftHandover.status == sh.HANDOVER_RECEIVED)
            .order_by(ShiftHandover.handed_over_at_iso.desc(), ShiftHandover.id.desc())
            .limit(limit)
        ).all()
    )
    out: list[ShiftHandover] = []
    for h in rows:
        if not _finite_non_negative_stock(h.hypochlorite_stock_liters):
            continue
        ho = (h.handed_over_at_iso or "").strip()
        rs = (h.received_at_iso or "").strip()
        ss = (h.shift_started_at_iso or "").strip()
        if not ho or not rs or not ss:
            continue
        if ss > ho:
            continue
        out.append(h)
    return out


def _sum_hipochlorite_truck_loads_liters(cargada_from_iso: str, cargada_to_iso_inclusive: str | None) -> float:
    """
    Suma `Entrega.cantidad` (litros) para entregas marcadas cargadas de hipoclorito,
    con `cargada_at_iso` en el intervalo inclusivo [from, to]. Si to es None, hasta `now_local_iso()`.
    """
    t_from = (cargada_from_iso or "").strip()
    if not t_from:
        return 0.0
    t_to = (cargada_to_iso_inclusive or "").strip() if cargada_to_iso_inclusive else sh.now_local_iso()
    if not t_to or t_from > t_to:
        return 0.0
    hipo = _hipo_product_sql_match()
    if hipo is None:
        return 0.0
    total = db.session.scalar(
        select(func.coalesce(func.sum(Entrega.cantidad), 0.0)).where(
            Entrega.estado == "cargada",
            Entrega.cargada_at_iso.isnot(None),
            func.trim(Entrega.cargada_at_iso) != "",
            Entrega.cargada_at_iso >= t_from,
            Entrega.cargada_at_iso <= t_to,
            hipo,
        )
    )
    try:
        v = float(total or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def _instant_from_handovers(handovers: list[ShiftHandover]) -> float | None:
    if not handovers:
        return None
    last = handovers[0]
    base = float(last.hypochlorite_stock_liters)
    cierre = (last.handed_over_at_iso or "").strip()
    if not cierre:
        return None
    loads = _sum_hipochlorite_truck_loads_liters(cierre, None)
    return base - loads


def _last_shift_production_from_handovers(handovers: list[ShiftHandover]) -> float | None:
    if len(handovers) < 2:
        return None
    last, prev = handovers[0], handovers[1]
    s_last = float(last.hypochlorite_stock_liters)
    s_prev = float(prev.hypochlorite_stock_liters)
    t0 = (last.shift_started_at_iso or "").strip()
    t1 = (last.handed_over_at_iso or "").strip()
    if not t0 or not t1 or t0 > t1:
        return None
    loads = _sum_hipochlorite_truck_loads_liters(t0, t1)
    return s_last - s_prev + loads


def get_instant_stock() -> float | None:
    """
    Stock instantáneo (litros): último stock informado en un cambio de turno recepcionado,
    menos cargas de camión de hipoclorito desde el cierre de ese turno (`handed_over_at_iso`) hasta ahora.
    """
    return _instant_from_handovers(_list_received_handovers_with_valid_stock())


def sum_hipochlorito_programada_liters(exclude_entrega_id: int | None = None) -> float:
    """
    Suma `Entrega.cantidad` (litros) de entregas en estado «programada» cuyo producto es hipoclorito
    (mismo criterio de nombre que el resto del módulo).
    """
    hipo = _hipo_product_sql_match()
    if hipo is None:
        return 0.0
    stmt = select(func.coalesce(func.sum(Entrega.cantidad), 0.0)).where(
        Entrega.estado == "programada",
        hipo,
    )
    if exclude_entrega_id is not None:
        stmt = stmt.where(Entrega.id != int(exclude_entrega_id))
    total = db.session.scalar(stmt)
    try:
        v = float(total or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def operational_liters_available_for_new_programada(exclude_entrega_id: int | None = None) -> float | None:
    """
    Litros que aún se pueden comprometer en nuevas entregas «programada» sin superar el stock
    instantáneo (mismo número que muestra el Panel). None si no hay base de turno válida (N/D).
    """
    instant = get_instant_stock()
    if instant is None:
        return None
    reserved = sum_hipochlorito_programada_liters(exclude_entrega_id)
    return max(0.0, float(instant) - float(reserved))


def get_last_shift_production() -> float | None:
    """
    Producción del último turno cerrado (litros):
    stock cierre último turno − stock cierre turno anterior + cargas de hipoclorito en
    [shift_started_at_iso, handed_over_at_iso] del último turno.
    """
    return _last_shift_production_from_handovers(_list_received_handovers_with_valid_stock())


def format_header_liters(value: float | None) -> str:
    """Texto para cabecera: entero con separador de miles '.' o 'N/D'."""
    if value is None:
        return "N/D"
    if not math.isfinite(value):
        return "N/D"
    n = int(round(value))
    return f"{n:,}".replace(",", ".") + " L"


def _fmt_iso_for_panel(iso: str | None) -> str | None:
    """ISO local guardado en BD → lectura breve en panel (sin parsear zona)."""
    s = (iso or "").strip()
    if not s:
        return None
    return s.replace("T", " ").strip()


def _pending_handover_panel_extra() -> tuple[str | None, int | None]:
    """
    Si hay entrega de turno sin recepcionar, el stock declarado no entra en los KPI
    (solo cuentan cierres recepcionados). Devuelve texto para el panel y el id para enlazar a recepción.
    """
    ho = sh.get_pending_handover()
    if ho is None:
        return None, None
    if not _finite_non_negative_stock(ho.hypochlorite_stock_liters):
        return None, None
    closed = _fmt_iso_for_panel(ho.handed_over_at_iso)
    liters = format_header_liters(float(ho.hypochlorite_stock_liters))
    msg = (
        f"Cambio de turno pendiente de recepción: se declaró {liters} de hipoclorito al cierre"
        + (f" ({closed})" if closed else "")
        + ". Los indicadores de producción y stock instantáneo solo se actualizan cuando el turno entrante recepciona el parte."
    )
    return msg, int(ho.id)


def _panel_shift_subnotes_from_handovers(handovers: list[ShiftHandover]) -> tuple[str | None, str | None]:
    """
    (leyenda stock según último cierre recepcionado, ventana del último turno para producción).
    """
    if not handovers:
        return None, None
    last = handovers[0]
    closed = _fmt_iso_for_panel(last.handed_over_at_iso)
    stock_note = f"Último stock informado (cierre recepcionado): {closed}" if closed else None
    t0 = _fmt_iso_for_panel(last.shift_started_at_iso)
    t1 = _fmt_iso_for_panel(last.handed_over_at_iso)
    if t0 and t1:
        prod_note = f"Período del turno: {t0} a {t1}"
    elif t1:
        prod_note = f"Cierre del turno: {t1}"
    else:
        prod_note = None
    return stock_note, prod_note


def header_operational_indicators_dict() -> dict[str, Any]:
    """
    Valores listos para plantilla; encapsula errores de BD para no tumbar la UI.
    """
    try:
        handovers = _list_received_handovers_with_valid_stock()
        instant = _instant_from_handovers(handovers)
        production = _last_shift_production_from_handovers(handovers)
        stock_note, prod_note = _panel_shift_subnotes_from_handovers(handovers)
        pending_notice, pending_id = _pending_handover_panel_extra()
        return {
            "instant_liters": instant,
            "last_shift_production_liters": production,
            "instant_display": format_header_liters(instant),
            "production_display": format_header_liters(production),
            "stock_panel_subnote": stock_note,
            "production_panel_subnote": prod_note,
            "pending_handover_notice": pending_notice,
            "pending_handover_id": pending_id,
            "ok": True,
        }
    except Exception:
        return {
            "instant_liters": None,
            "last_shift_production_liters": None,
            "instant_display": "N/D",
            "production_display": "N/D",
            "stock_panel_subnote": None,
            "production_panel_subnote": None,
            "pending_handover_notice": None,
            "pending_handover_id": None,
            "ok": False,
        }
