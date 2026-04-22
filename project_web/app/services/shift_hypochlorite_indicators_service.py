"""
Indicadores de hipoclorito (litros) según reglas operativas fijas (Panel, Entregas, cabecera).

Punto de entrada para rutas: `app.services.operational_informed_stock`.

Definición obligatoria (no mezclar con otras fórmulas):

**PRODUCCIÓN (último turno con cierre recepcionado)**
  = stock final − stock inicial + cargas en el turno − ingresos PT admin en el turno
  = `hypochlorite` del cierre de ese partido − cierre inmediatamente anterior
    + entregas «cargada» hipo con `cargada_at_iso` en [inicio, cierre del turno]
    − `sum_hipo_administrador_pt_ingresos` en el mismo intervalo
  (las cargas bajaron el stock y se re-suman; los ingresos admin lo inflaron y se restan.)

**STOCK INSTANTÁNEO**
  = stock al inicio del turno en análisis − cargas (entregas «cargada») + ingresos de PT
  de hipoclorito con `cargado_por` = usuario **administrador** (`User.is_admin`),
  todos contados **desde el inicio operativo** de ese turno hasta ahora (ISO local).

- Stock al inicio del turno: lo declarado al **cierre recepcionado inmediatamente anterior**
  (última fila `shift_handovers` con status received y stock válido); es el volumen con el que
  arrancó el turno en curso o el de la partida pendiente.
- Inicio operativo (ancla T0): inicio de sesión de turno del `ShiftHandover` pendiente de
  recepción si existe; si no, `started_at_iso` de la `ShiftSession` abierta; si no hay
  ni pendiente ni sesión, `received_at_iso` del último turno recepcionado.
- Cargas: `Entrega` con estado `cargada`, producto hipoclorito, `cargada_at_iso` en [T0, ahora].
- Ingresos administrativos: `ingresos_stock` PT + join a `User.is_admin` + ventana de tiempo.

Las entregas «programada» se comparan con el techo de stock instantáneo
(`operational_liters_available_for_new_programada`).

`ingresos_stock` / `consumos_stock` (lotes) distintos de esta vista operativa.
"""
from __future__ import annotations

import math
from typing import Any, Tuple

from sqlalchemy import func, select
from app.constants import ENTREGAS_STOCK_CATEGORIA
from app.extensions import db
from app.models import Entrega, IngresoStock, ShiftHandover, User
from app.services import shift_handover_service as sh
from app.utils.hipoclorito_producto import entrega_columna_es_hipoclorito_operativo_sql


def _finite_non_negative_stock(v: Any) -> bool:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and x >= 0.0


def _hipo_product_sql_match():
    """Entregas cuyo `producto` es hipoclorito operativo (cualquier alias)."""
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


def sum_hipo_administrador_pt_ingresos_in_interval(
    t_from_inclusive: str, t_to_inclusive: str | None
) -> float:
    """
    Suma `IngresoStock.cantidad` (L) de categoría producto terminado, producto hipoclorito
    operativo, con `cargado_por_user_id` apuntando a un usuario con `is_admin` True, y
    `created_at_iso` en [t_from, t_to] (t_to = ahora operativa local si se omite).
    """
    t0 = (t_from_inclusive or "").strip()
    t1 = (t_to_inclusive or "").strip() if t_to_inclusive else sh.now_local_iso()
    if not t0 or not t1 or t0 > t1:
        return 0.0
    hipo = entrega_columna_es_hipoclorito_operativo_sql(IngresoStock.producto)
    if hipo is None:
        return 0.0
    total = db.session.scalar(
        select(func.coalesce(func.sum(IngresoStock.cantidad), 0.0))
        .select_from(IngresoStock)
        .join(User, IngresoStock.cargado_por_user_id == User.id)
        .where(
            IngresoStock.categoria == ENTREGAS_STOCK_CATEGORIA,
            hipo,
            User.is_admin.is_(True),
            IngresoStock.cargado_por_user_id.isnot(None),
            IngresoStock.created_at_iso >= t0,
            IngresoStock.created_at_iso <= t1,
        )
    )
    try:
        v = float(total or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


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


def _resolve_s0_t0_instant(
    handovers: list[ShiftHandover],
) -> Tuple[float, str] | None:
    """
    Stock al inicio del turno en curso = cierre del último handover recepcionado; ancla
    de tiempo T0 según partida pendiente, sesión abierta o, en última instancia, recepción.
    """
    if not handovers:
        return None
    s0 = float(handovers[0].hypochlorite_stock_liters)
    pending = sh.get_pending_handover()
    if pending is not None and _finite_non_negative_stock(pending.hypochlorite_stock_liters):
        t0 = (pending.shift_started_at_iso or "").strip()
        if t0:
            return s0, t0
    open_s = sh.get_open_shift_session()
    if open_s is not None:
        t0 = (open_s.started_at_iso or "").strip()
        if t0:
            return s0, t0
    t0 = (handovers[0].received_at_iso or "").strip()
    if t0:
        return s0, t0
    return None


def _instant_from_handovers(handovers: list[ShiftHandover]) -> float | None:
    pair = _resolve_s0_t0_instant(handovers)
    if pair is None:
        return None
    s0, t0 = pair
    loads = _sum_hipochlorite_truck_loads_liters(t0, None)
    ingr = sum_hipo_administrador_pt_ingresos_in_interval(t0, None)
    v = s0 - loads + ingr
    if not math.isfinite(v):
        return None
    return v


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
    ingr = sum_hipo_administrador_pt_ingresos_in_interval(t0, t1)
    p = s_last - s_prev + loads - ingr
    return p if math.isfinite(p) else None


def get_instant_stock() -> float | None:
    """
    Stock instantáneo: stock al inicio del turno (último cierre recepcionado)
    − cargas reales (entregas 'cargada') + ingresos PT de hipoclorito hechos por administrador,
    en la ventana [inicio operativo de turno, ahora] (criterio detallado en el docstring del módulo).
    """
    return _instant_from_handovers(_list_received_handovers_with_valid_stock())


def sum_hipochlorito_programada_liters(exclude_entrega_id: int | None = None) -> float:
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
    instant = get_instant_stock()
    if instant is None:
        return None
    reserved = sum_hipochlorito_programada_liters(exclude_entrega_id)
    return max(0.0, float(instant) - float(reserved))


def get_last_shift_production() -> float | None:
    """
    Producción del turno cuyo cierre es el último partido recepcionado:
    stock final − stock inicial + cargas hipo (ventana [inicio, cierre] del turno)
    − ingresos PT por administrador en esa misma ventana.
    Solo con dos o más cierres recepcionados válidos; si no, None (no inventar cierre).
    """
    return _last_shift_production_from_handovers(_list_received_handovers_with_valid_stock())


def format_header_liters(value: float | None) -> str:
    if value is None:
        return "N/D"
    if not math.isfinite(value):
        return "N/D"
    n = int(round(value))
    return f"{n:,}".replace(",", ".") + " L"


def _fmt_iso_for_panel(iso: str | None) -> str | None:
    s = (iso or "").strip()
    if not s:
        return None
    return s.replace("T", " ").strip()


def _pending_handover_panel_extra() -> tuple[str | None, int | None]:
    ho = sh.get_pending_handover()
    if ho is None:
        return None, None
    if not _finite_non_negative_stock(ho.hypochlorite_stock_liters):
        return None, None
    closed = _fmt_iso_for_panel(ho.handed_over_at_iso)
    liters = format_header_liters(float(ho.hypochlorite_stock_liters))
    msg = (
        f"Entrega de turno sin recepcionar: {liters} de hipoclorito declarado al cierre"
        + (f" ({closed})" if closed else "")
        + ". Recepcioná el parte para continuar el ciclo. La producción del panel sigue "
        "siendo del último turno ya recepcionado; el stock instantáneo se calcula con el turno en trámite o el en curso."
    )
    return msg, int(ho.id)


def _panel_shift_subnotes_from_handovers(handovers: list[ShiftHandover]) -> tuple[str | None, str | None, str | None]:
    if not handovers:
        return None, None, None
    last = handovers[0]
    t0i = _fmt_iso_for_panel(last.shift_started_at_iso)
    t1i = _fmt_iso_for_panel(last.handed_over_at_iso)
    prod_note: str | None
    if t0i and t1i:
        prod_note = (
            f"Turno cerrado (recepcionado): inicio {t0i} — cierre {t1i}. "
            "Producción = (stock cierre − stock apertura) + cargas del período − ingresos PT (admin) del mismo período."
        )
    elif t1i:
        prod_note = f"Cierre del turno: {t1i}."
    else:
        prod_note = None
    recv = _fmt_iso_for_panel(last.received_at_iso)
    ancla = "Inicio de turno: stock = último cierre recepcionado"
    if recv:
        ancla += f" (recepcionado: {recv})."
    else:
        ancla += "."
    stock_note = (
        f"{ancla} Instantáneo = ese volumen "
        "− entregas «cargada» (hipo) + ingresos de PT hechos con usuario administrador, desde el inicio operativo de turno."
    )
    kpi_legend = (
        "Producción del turno: stock final − stock inicial + cargas (camión) − ingresos PT por administrador, "
        "todos en [inicio, cierre] de ese turno. "
        "Stock instantáneo: stock al inicio del turno en curso − cargas + ingresos admin desde el inicio operativo hasta ahora. "
        "No se usa el saldo teórico por lotes de existencias."
    )
    return stock_note, prod_note, kpi_legend


def header_operational_indicators_dict() -> dict[str, Any]:
    try:
        handovers = _list_received_handovers_with_valid_stock()
        instant = _instant_from_handovers(handovers)
        production = _last_shift_production_from_handovers(handovers)
        stock_note, prod_note, kpi_legend = _panel_shift_subnotes_from_handovers(handovers)
        pending_notice, pending_id = _pending_handover_panel_extra()
        open_s = sh.get_open_shift_session()
        production_scope_subnote: str | None = None
        if open_s is not None and production is not None:
            production_scope_subnote = (
                "Turno en curso: el número de producción corresponde al último turno "
                "ya cerrado y recepcionado (la producción del turno actual se informa al cierre de turno)."
            )
        elif open_s is not None and production is None and len(handovers) < 2:
            production_scope_subnote = (
                "Producción disponible al cierre: hace falta al menos un turno completo recepcionado "
                "con dos cierres encadenados en el registro; el turno actual aún no tiene cierre."
            )
        return {
            "instant_liters": instant,
            "last_shift_production_liters": production,
            "instant_display": format_header_liters(instant),
            "production_display": format_header_liters(production),
            "stock_panel_subnote": stock_note,
            "production_panel_subnote": prod_note,
            "production_scope_subnote": production_scope_subnote,
            "kpi_definitions_legend": kpi_legend,
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
            "production_scope_subnote": None,
            "kpi_definitions_legend": None,
            "pending_handover_notice": None,
            "pending_handover_id": None,
            "ok": False,
        }
