"""Estadísticas de operadores para el panel: atrasos en análisis y producción mensual."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.constants import AGUA_ANALYSIS_INTERVAL_SECONDS, ANALYSIS_INTERVAL_SECONDS, MODULE_LABELS
from app.extensions import db
from app.models import (
    AguaRegistro,
    ReactorRegistro,
    SalmueraAnalisis8hs,
    SalmueraRegistro,
    ShiftHandover,
)
from app.services import shift_handover_service as sh
from app.services.plant_stop_service import (
    CIRCUIT_AGUA,
    CIRCUIT_REACTOR,
    circuit_key_for_electrolizador,
    pause_seconds_after_anchor,
)
from app.services.salmuera_analisis_8hs_service import ANALISIS_8HS_INTERVAL_SECONDS
from app.services.shift_hypochlorite_indicators_service import (
    format_header_liters,
    sum_hipo_administrador_pt_ingresos_in_interval,
)
from app.utils.datetime_operacion import now_operacion_naive_local

_ANALISIS_LABELS: dict[str, str] = {
    "hipoclorito_e2": f"{MODULE_LABELS['salmuera']} · Electrolizador 2",
    "hipoclorito_e3": f"{MODULE_LABELS['salmuera']} · Electrolizador 3",
    "reactor": MODULE_LABELS["reactor"],
    "agua": MODULE_LABELS["agua"],
    "analisis_8hs": "Análisis 8 hs (dureza / cloro libre)",
}

_MONTHS_ES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def _parse_iso(iso: str | None) -> datetime | None:
    s = (iso or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s[:26])
    except ValueError:
        return None


def _month_label(year: int, month: int) -> str:
    if 1 <= month <= 12:
        return f"{_MONTHS_ES[month]} {year}"
    return f"{year}-{month:02d}"


def _month_bounds_iso(year: int, month: int) -> tuple[str, str]:
    """Inicio inclusivo y fin exclusivo del mes (ISO local naive)."""
    start = f"{year:04d}-{month:02d}-01T00:00:00"
    if month == 12:
        end = f"{year + 1:04d}-01-01T00:00:00"
    else:
        end = f"{year:04d}-{month + 1:02d}-01T00:00:00"
    return start, end


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _in_range(ts: str | None, start: str, end_exclusive: str) -> bool:
    s = (ts or "").strip()
    return bool(s and start <= s < end_exclusive)


def _was_analysis_delayed(
    prev_created_iso: str | None,
    curr_created_iso: str,
    interval_sec: int,
    circuit_key: str,
) -> bool:
    prev = (prev_created_iso or "").strip()
    curr = (curr_created_iso or "").strip()
    if not curr:
        return False
    if not prev:
        return False
    prev_dt = _parse_iso(prev)
    curr_dt = _parse_iso(curr)
    if prev_dt is None or curr_dt is None:
        return False
    pause_extra = pause_seconds_after_anchor(prev, circuit_key, now_iso=curr)
    due_ts = prev_dt.timestamp() + int(interval_sec) + pause_extra
    return curr_dt.timestamp() > due_ts


def _norm_operador(name: str | None) -> str:
    return (name or "").strip() or "—"


def _accum_delay(
    counts: dict[str, dict[str, int]],
    operador: str,
    tipo: str,
) -> None:
    op = _norm_operador(operador)
    if op not in counts:
        counts[op] = defaultdict(int)
    counts[op][tipo] += 1
    counts[op]["_total"] += 1


def _scan_consecutive_delays(
    rows: list[tuple[str, str, str]],
    interval_sec: int,
    circuit_key: str,
    tipo: str,
    counts: dict[str, dict[str, int]],
    *,
    start_iso: str,
    end_exclusive: str,
    ts_attr_index: int = 1,
    operador_index: int = 0,
    extra_delay_check: Any | None = None,
) -> None:
    prev_ts: str | None = None
    for row in rows:
        operador = row[operador_index]
        ts = row[ts_attr_index]
        if not _in_range(ts, start_iso, end_exclusive):
            prev_ts = ts
            continue
        delayed = False
        if extra_delay_check and extra_delay_check(row):
            delayed = True
        elif _was_analysis_delayed(prev_ts, ts, interval_sec, circuit_key):
            delayed = True
        if delayed:
            _accum_delay(counts, operador, tipo)
        prev_ts = ts


def ranking_atrasos_analisis(
    *,
    desde_iso: str,
    hasta_iso_exclusive: str,
) -> list[dict[str, Any]]:
    """
    Ranking de operadores por cantidad de análisis registrados con atraso en el período.
    ``hasta_iso_exclusive`` es límite superior exclusivo (p. ej. primer día del mes siguiente).
    """
    counts: dict[str, dict[str, int]] = {}

    hip_rows = db.session.execute(
        select(
            SalmueraRegistro.operador,
            SalmueraRegistro.created_at_iso,
            SalmueraRegistro.electrolizador,
            SalmueraRegistro.atraso_motivo,
        ).order_by(SalmueraRegistro.electrolizador.asc(), SalmueraRegistro.created_at_iso.asc(), SalmueraRegistro.id.asc())
    ).all()

    by_e: dict[int, list[tuple[str, str, str, str | None]]] = defaultdict(list)
    for operador, created, electrolizador, motivo in hip_rows:
        by_e[int(electrolizador)].append((operador, created, str(electrolizador), motivo))

    for eid, rows in by_e.items():
        try:
            ck = circuit_key_for_electrolizador(eid)
        except ValueError:
            continue
        tipo = f"hipoclorito_e{eid}"
        if tipo not in _ANALISIS_LABELS:
            _ANALISIS_LABELS[tipo] = f"{MODULE_LABELS['salmuera']} · Electrolizador {eid}"
        prev_ts: str | None = None
        for operador, created, _e, motivo in rows:
            if not _in_range(created, desde_iso, hasta_iso_exclusive):
                prev_ts = created
                continue
            delayed = bool((motivo or "").strip()) or _was_analysis_delayed(
                prev_ts, created, int(ANALYSIS_INTERVAL_SECONDS), ck
            )
            if delayed:
                _accum_delay(counts, operador, tipo)
            prev_ts = created

    reactor_rows = db.session.execute(
        select(ReactorRegistro.operador, ReactorRegistro.created_at_iso).order_by(
            ReactorRegistro.created_at_iso.asc(), ReactorRegistro.id.asc()
        )
    ).all()
    _scan_consecutive_delays(
        [(op, ts, "reactor") for op, ts in reactor_rows],
        int(ANALYSIS_INTERVAL_SECONDS),
        CIRCUIT_REACTOR,
        "reactor",
        counts,
        start_iso=desde_iso,
        end_exclusive=hasta_iso_exclusive,
    )

    agua_rows = db.session.execute(
        select(AguaRegistro.operador, AguaRegistro.created_at_iso).order_by(
            AguaRegistro.created_at_iso.asc(), AguaRegistro.id.asc()
        )
    ).all()
    _scan_consecutive_delays(
        [(op, ts, "agua") for op, ts in agua_rows],
        int(AGUA_ANALYSIS_INTERVAL_SECONDS),
        CIRCUIT_AGUA,
        "agua",
        counts,
        start_iso=desde_iso,
        end_exclusive=hasta_iso_exclusive,
    )

    a8_rows = db.session.execute(
        select(
            SalmueraAnalisis8hs.operador,
            SalmueraAnalisis8hs.fecha_hora_iso,
        ).order_by(SalmueraAnalisis8hs.fecha_hora_iso.asc(), SalmueraAnalisis8hs.id.asc())
    ).all()
    _scan_consecutive_delays(
        [(op, ts, "analisis_8hs") for op, ts in a8_rows],
        int(ANALISIS_8HS_INTERVAL_SECONDS),
        CIRCUIT_REACTOR,
        "analisis_8hs",
        counts,
        start_iso=desde_iso,
        end_exclusive=hasta_iso_exclusive,
    )

    ranking: list[dict[str, Any]] = []
    for operador, tipos in counts.items():
        total = int(tipos.get("_total", 0))
        desglose: list[dict[str, Any]] = []
        for key, n in sorted(tipos.items(), key=lambda kv: (-kv[1], kv[0])):
            if key == "_total" or n <= 0:
                continue
            desglose.append(
                {
                    "tipo": key,
                    "label": _ANALISIS_LABELS.get(key, key),
                    "count": int(n),
                }
            )
        ranking.append(
            {
                "operador": operador,
                "total_atrasos": total,
                "desglose": desglose,
            }
        )
    ranking.sort(key=lambda r: (-r["total_atrasos"], r["operador"].lower()))
    return ranking


def _shift_production_liters(current: ShiftHandover, previous: ShiftHandover) -> float | None:
    t0 = (current.shift_started_at_iso or "").strip()
    t1 = (current.handed_over_at_iso or "").strip()
    if not t0 or not t1 or t0 > t1:
        return None
    try:
        s_last = float(current.hypochlorite_stock_liters)
        s_prev = float(previous.hypochlorite_stock_liters)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(s_last) or not math.isfinite(s_prev):
        return None
    from app.services.shift_hypochlorite_indicators_service import _sum_hipochlorite_truck_loads_liters

    loads = _sum_hipochlorite_truck_loads_liters(t0, t1)
    ingr = sum_hipo_administrador_pt_ingresos_in_interval(t0, t1)
    p = s_last - s_prev + loads - ingr
    return p if math.isfinite(p) else None


def _list_received_handovers_chronological(limit: int = 500) -> list[ShiftHandover]:
    rows = list(
        db.session.scalars(
            select(ShiftHandover)
            .options(joinedload(ShiftHandover.outgoing_user))
            .where(ShiftHandover.status == sh.HANDOVER_RECEIVED)
            .order_by(ShiftHandover.handed_over_at_iso.asc(), ShiftHandover.id.asc())
            .limit(limit)
        ).all()
    )
    out: list[ShiftHandover] = []
    for h in rows:
        ho = (h.handed_over_at_iso or "").strip()
        rs = (h.received_at_iso or "").strip()
        ss = (h.shift_started_at_iso or "").strip()
        if not ho or not rs or not ss or ss > ho:
            continue
        try:
            v = float(h.hypochlorite_stock_liters)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v) or v < 0:
            continue
        out.append(h)
    return out


def produccion_por_operador_en_mes(year: int, month: int) -> dict[str, Any]:
    """
    Suma producción de hipoclorito (L) por operador saliente de turno en el mes,
    usando la misma fórmula del panel por cada cierre recepcionado.
    """
    start, end = _month_bounds_iso(year, month)
    handovers = _list_received_handovers_chronological()
    by_operador: dict[str, float] = defaultdict(float)
    turnos_por_operador: dict[str, int] = defaultdict(int)
    turnos_total = 0
    for i in range(1, len(handovers)):
        curr = handovers[i]
        prev = handovers[i - 1]
        ho = (curr.handed_over_at_iso or "").strip()
        if not _in_range(ho, start, end):
            continue
        prod = _shift_production_liters(curr, prev)
        if prod is None:
            continue
        user = curr.outgoing_user
        op_name = _norm_operador(user.username if user else None)
        by_operador[op_name] += prod
        turnos_por_operador[op_name] += 1
        turnos_total += 1

    operadores: list[dict[str, Any]] = []
    for op, liters in sorted(by_operador.items(), key=lambda kv: (-kv[1], kv[0].lower())):
        n_turnos = turnos_por_operador[op]
        promedio_turno = liters / n_turnos if n_turnos else 0.0
        operadores.append(
            {
                "operador": op,
                "produccion_liters": round(liters, 1),
                "produccion_display": format_header_liters(liters),
                "turnos": n_turnos,
                "promedio_por_turno_liters": round(promedio_turno, 1),
                "promedio_por_turno_display": format_header_liters(promedio_turno),
            }
        )

    total_liters = sum(by_operador.values())
    n_ops = len(by_operador)
    promedio_operador = total_liters / n_ops if n_ops else 0.0

    return {
        "year": year,
        "month": month,
        "label": _month_label(year, month),
        "desde_iso": start,
        "hasta_iso_exclusive": end,
        "operadores": operadores,
        "total_liters": round(total_liters, 1),
        "total_display": format_header_liters(total_liters),
        "promedio_por_operador_liters": round(promedio_operador, 1),
        "promedio_por_operador_display": format_header_liters(promedio_operador),
        "turnos_contados": turnos_total,
    }


def build_operador_dashboard_context() -> dict[str, Any]:
    now = now_operacion_naive_local()
    cy, cm = now.year, now.month
    py, pm = _prev_month(cy, cm)

    mes_actual = produccion_por_operador_en_mes(cy, cm)
    mes_anterior = produccion_por_operador_en_mes(py, pm)

    # Ranking de atrasos: últimos 90 días (ventana amplia para detectar patrones)
    desde_ranking = (now - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00")
    hasta_ranking = now_operacion_naive_local().isoformat(timespec="seconds")

    ranking = ranking_atrasos_analisis(desde_iso=desde_ranking, hasta_iso_exclusive=hasta_ranking)

    return {
        "mes_actual": mes_actual,
        "mes_anterior": mes_anterior,
        "ranking_atrasos": ranking,
        "ranking_periodo_label": "últimos 90 días",
        "ranking_desde_iso": desde_ranking,
        "ranking_hasta_iso": hasta_ranking,
    }
