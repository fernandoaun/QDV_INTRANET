"""Estadísticas de operadores para el panel: atrasos en análisis y producción mensual."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

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


def _analysis_delay_seconds(
    prev_created_iso: str | None,
    curr_created_iso: str,
    interval_sec: int,
    circuit_key: str,
) -> int:
    """Segundos de atraso (0 si el registro no está vencido o no hay ancla previa)."""
    prev = (prev_created_iso or "").strip()
    curr = (curr_created_iso or "").strip()
    if not prev or not curr:
        return 0
    prev_dt = _parse_iso(prev)
    curr_dt = _parse_iso(curr)
    if prev_dt is None or curr_dt is None:
        return 0
    pause_extra = pause_seconds_after_anchor(prev, circuit_key, now_iso=curr)
    due_ts = prev_dt.timestamp() + int(interval_sec) + pause_extra
    overdue = curr_dt.timestamp() - due_ts
    return max(0, int(overdue))


def _was_analysis_delayed(
    prev_created_iso: str | None,
    curr_created_iso: str,
    interval_sec: int,
    circuit_key: str,
) -> bool:
    return _analysis_delay_seconds(prev_created_iso, curr_created_iso, interval_sec, circuit_key) > 0


def format_atraso_duration(seconds: int) -> str:
    """Duración legible de atraso (p. ej. ``2 h 15 min`` o ``45 min``)."""
    s = max(0, int(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h >= 1:
        return f"{h} h {m} min" if m else f"{h} h"
    if m >= 1:
        return f"{m} min {sec} s" if sec else f"{m} min"
    return f"{sec} s"


def _norm_operador(name: str | None) -> str:
    return (name or "").strip() or "—"


def _empty_delay_bucket() -> dict[str, int]:
    return defaultdict(int)


def _accum_delay(
    counts: dict[str, dict[str, int]],
    seconds_map: dict[str, dict[str, int]],
    operador: str,
    tipo: str,
    delay_seconds: int,
) -> None:
    op = _norm_operador(operador)
    if op not in counts:
        counts[op] = _empty_delay_bucket()
        seconds_map[op] = _empty_delay_bucket()
    counts[op][tipo] += 1
    counts[op]["_total"] += 1
    sec = max(0, int(delay_seconds))
    seconds_map[op][tipo] += sec
    seconds_map[op]["_total"] += sec


def _scan_consecutive_delays(
    rows: list[tuple[str, str, str]],
    interval_sec: int,
    circuit_key: str,
    tipo: str,
    counts: dict[str, dict[str, int]],
    seconds_map: dict[str, dict[str, int]],
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
        delay_sec = _analysis_delay_seconds(prev_ts, ts, interval_sec, circuit_key)
        delayed = delay_sec > 0
        if extra_delay_check and extra_delay_check(row):
            delayed = True
        if delayed:
            _accum_delay(counts, seconds_map, operador, tipo, delay_sec)
        prev_ts = ts


def ranking_atrasos_analisis(
    *,
    desde_iso: str,
    hasta_iso_exclusive: str,
) -> list[dict[str, Any]]:
    """
    Ranking de operadores por atrasos en análisis en el período (cantidad y tiempo acumulado).
    ``hasta_iso_exclusive`` es límite superior exclusivo (p. ej. primer día del mes siguiente).
    """
    counts: dict[str, dict[str, int]] = {}
    seconds_map: dict[str, dict[str, int]] = {}

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
            delay_sec = _analysis_delay_seconds(
                prev_ts, created, int(ANALYSIS_INTERVAL_SECONDS), ck
            )
            delayed = bool((motivo or "").strip()) or delay_sec > 0
            if delayed:
                _accum_delay(counts, seconds_map, operador, tipo, delay_sec)
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
        seconds_map,
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
        seconds_map,
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
        seconds_map,
        start_iso=desde_iso,
        end_exclusive=hasta_iso_exclusive,
    )

    ranking: list[dict[str, Any]] = []
    for operador, tipos in counts.items():
        total = int(tipos.get("_total", 0))
        total_sec = int(seconds_map.get(operador, {}).get("_total", 0))
        desglose: list[dict[str, Any]] = []
        secs_by_tipo = seconds_map.get(operador, {})
        for key, n in sorted(tipos.items(), key=lambda kv: (-kv[1], kv[0])):
            if key == "_total" or n <= 0:
                continue
            tipo_sec = int(secs_by_tipo.get(key, 0))
            desglose.append(
                {
                    "tipo": key,
                    "label": _ANALISIS_LABELS.get(key, key),
                    "count": int(n),
                    "segundos_atraso": tipo_sec,
                    "tiempo_display": format_atraso_duration(tipo_sec),
                    "promedio_display": format_atraso_duration(tipo_sec // n if n else 0),
                }
            )
        promedio_sec = total_sec // total if total else 0
        ranking.append(
            {
                "operador": operador,
                "total_atrasos": total,
                "total_segundos_atraso": total_sec,
                "tiempo_atraso_total_display": format_atraso_duration(total_sec),
                "promedio_atraso_display": format_atraso_duration(promedio_sec),
                "desglose": desglose,
            }
        )
    ranking.sort(
        key=lambda r: (-r["total_segundos_atraso"], -r["total_atrasos"], r["operador"].lower())
    )
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


@dataclass(frozen=True)
class _CampoAnalisisSpec:
    key: str
    label: str
    threshold_op: str | None = None
    threshold: float | None = None
    umbral_label: str | None = None


def _campo_desviado(value: float, spec: _CampoAnalisisSpec) -> bool:
    if spec.threshold_op is None or spec.threshold is None:
        return False
    if spec.threshold_op == "gt":
        return value > spec.threshold
    if spec.threshold_op == "lt":
        return value < spec.threshold
    return False


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _promedio_campos(
    rows: list[Any],
    specs: tuple[_CampoAnalisisSpec, ...],
    getter: Callable[[Any, str], Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in specs:
        vals: list[float] = []
        desvios = 0
        for row in rows:
            fv = _safe_float(getter(row, spec.key))
            if fv is None:
                continue
            vals.append(fv)
            if _campo_desviado(fv, spec):
                desvios += 1
        if not vals:
            continue
        promedio = sum(vals) / len(vals)
        out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "promedio": round(promedio, 2),
                "registros": len(vals),
                "desvios": desvios,
                "umbral_label": spec.umbral_label,
                "tiene_umbral": spec.umbral_label is not None,
            }
        )
    return out


_HIPO_CAMPOS: tuple[_CampoAnalisisSpec, ...] = (
    _CampoAnalisisSpec("amperaje", "Amperaje"),
    _CampoAnalisisSpec("voltaje_total", "V Σ celdas"),
    _CampoAnalisisSpec("voltaje_total_trafo", "V trafo"),
    _CampoAnalisisSpec("caudal_agua_l_h", "Caudal agua (L/h)"),
    _CampoAnalisisSpec("caudal_salmuera_l_h", "Caudal salmuera (L/h)"),
    _CampoAnalisisSpec("hipo_conc", "Hipo conc"),
    _CampoAnalisisSpec("hipo_exceso_soda", "Exceso soda", "gt", 9.0, "> 9"),
    _CampoAnalisisSpec("sal_temp", "Temp. salmuera"),
    _CampoAnalisisSpec("sal_conc", "Conc. salmuera", "lt", 260.0, "< 260 g/L"),
    _CampoAnalisisSpec("sal_ph", "pH salmuera", "gt", 5.0, "> 5"),
    _CampoAnalisisSpec("soda_conc", "Conc. soda"),
    _CampoAnalisisSpec("declor_ph", "pH declor.", "gt", 1.9, "> 1.9"),
    _CampoAnalisisSpec("orp", "ORP"),
)

_REACTOR_CAMPOS: tuple[_CampoAnalisisSpec, ...] = (
    _CampoAnalisisSpec("ph", "pH"),
    _CampoAnalisisSpec("temperatura", "Temperatura"),
    _CampoAnalisisSpec("densidad", "Densidad"),
    _CampoAnalisisSpec("concentracion_tabla", "Conc. salmuera", "lt", 200.0, "< 200"),
    _CampoAnalisisSpec("exceso_naoh", "Exceso soda", "gt", 0.16, "> 0.16"),
    _CampoAnalisisSpec("exceso_na2co3", "Exceso carbonato", "gt", 0.45, "> 0.45"),
    _CampoAnalisisSpec("orp", "ORP"),
)

_AGUA_CAMPOS: tuple[_CampoAnalisisSpec, ...] = (
    _CampoAnalisisSpec("temperatura", "Temperatura"),
    _CampoAnalisisSpec("dureza", "Dureza", "gt", 1.0, "> 1 ppm"),
    _CampoAnalisisSpec("numero_columna", "Columna"),
)

_ANALISIS_8HS_CAMPOS: tuple[_CampoAnalisisSpec, ...] = (
    _CampoAnalisisSpec("dureza_salmuera", "Dureza salmuera"),
    _CampoAnalisisSpec("cloro_libre_salmuera", "Cloro libre"),
)


def _getter_attr(row: Any, key: str) -> Any:
    return getattr(row, key, None)


def analisis_promedios_por_operador_en_mes(year: int, month: int) -> dict[str, list[dict[str, Any]]]:
    """
    Promedios de análisis por operador en el mes, con conteo de desvíos (umbrales operativos).
    Excluye voltajes por celda individual; incluye V Σ celdas y V trafo.
    """
    start, end = _month_bounds_iso(year, month)

    hip_rows = db.session.scalars(
        select(SalmueraRegistro)
        .where(SalmueraRegistro.created_at_iso >= start, SalmueraRegistro.created_at_iso < end)
        .order_by(SalmueraRegistro.created_at_iso.asc(), SalmueraRegistro.id.asc())
    ).all()

    by_op_e: dict[tuple[str, int], list[SalmueraRegistro]] = defaultdict(list)
    for r in hip_rows:
        op = _norm_operador(r.operador)
        by_op_e[(op, int(r.electrolizador))].append(r)

    reactor_rows = db.session.scalars(
        select(ReactorRegistro)
        .where(ReactorRegistro.created_at_iso >= start, ReactorRegistro.created_at_iso < end)
        .order_by(ReactorRegistro.created_at_iso.asc(), ReactorRegistro.id.asc())
    ).all()
    by_op_reactor: dict[str, list[ReactorRegistro]] = defaultdict(list)
    for r in reactor_rows:
        by_op_reactor[_norm_operador(r.operador)].append(r)

    agua_rows = db.session.scalars(
        select(AguaRegistro)
        .where(AguaRegistro.created_at_iso >= start, AguaRegistro.created_at_iso < end)
        .order_by(AguaRegistro.created_at_iso.asc(), AguaRegistro.id.asc())
    ).all()
    by_op_agua: dict[str, list[AguaRegistro]] = defaultdict(list)
    for r in agua_rows:
        by_op_agua[_norm_operador(r.operador)].append(r)

    a8_rows = db.session.scalars(
        select(SalmueraAnalisis8hs)
        .where(SalmueraAnalisis8hs.fecha_hora_iso >= start, SalmueraAnalisis8hs.fecha_hora_iso < end)
        .order_by(SalmueraAnalisis8hs.fecha_hora_iso.asc(), SalmueraAnalisis8hs.id.asc())
    ).all()
    by_op_a8: dict[str, list[SalmueraAnalisis8hs]] = defaultdict(list)
    for r in a8_rows:
        by_op_a8[_norm_operador(r.operador)].append(r)

    all_ops: set[str] = set()
    all_ops.update(op for op, _ in by_op_e)
    all_ops.update(by_op_reactor)
    all_ops.update(by_op_agua)
    all_ops.update(by_op_a8)

    por_operador: dict[str, list[dict[str, Any]]] = {}
    for op in sorted(all_ops, key=lambda s: s.lower()):
        bloques: list[dict[str, Any]] = []
        for eid in sorted({e for o, e in by_op_e if o == op}):
            rows_e = by_op_e[(op, eid)]
            campos = _promedio_campos(rows_e, _HIPO_CAMPOS, _getter_attr)
            if campos:
                bloques.append(
                    {
                        "tipo": f"hipoclorito_e{eid}",
                        "label": f"{MODULE_LABELS['salmuera']} · Electrolizador {eid}",
                        "registros": len(rows_e),
                        "campos": campos,
                        "total_desvios": sum(c["desvios"] for c in campos),
                    }
                )
        if op in by_op_reactor:
            rows_r = by_op_reactor[op]
            campos = _promedio_campos(rows_r, _REACTOR_CAMPOS, _getter_attr)
            if campos:
                bloques.append(
                    {
                        "tipo": "reactor",
                        "label": MODULE_LABELS["reactor"],
                        "registros": len(rows_r),
                        "campos": campos,
                        "total_desvios": sum(c["desvios"] for c in campos),
                    }
                )
        if op in by_op_agua:
            rows_a = by_op_agua[op]
            campos = _promedio_campos(rows_a, _AGUA_CAMPOS, _getter_attr)
            if campos:
                bloques.append(
                    {
                        "tipo": "agua",
                        "label": MODULE_LABELS["agua"],
                        "registros": len(rows_a),
                        "campos": campos,
                        "total_desvios": sum(c["desvios"] for c in campos),
                    }
                )
        if op in by_op_a8:
            rows_8 = by_op_a8[op]
            campos = _promedio_campos(rows_8, _ANALISIS_8HS_CAMPOS, _getter_attr)
            if campos:
                bloques.append(
                    {
                        "tipo": "analisis_8hs",
                        "label": "Análisis 8 hs",
                        "registros": len(rows_8),
                        "campos": campos,
                        "total_desvios": sum(c["desvios"] for c in campos),
                    }
                )
        if bloques:
            por_operador[op] = bloques

    return por_operador


def _produccion_lookup(mes_prod: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {o["operador"]: o for o in mes_prod.get("operadores", [])}


def reporte_operador_mes(year: int, month: int) -> dict[str, Any]:
    """Reporte mensual por operador: producción + promedios de análisis con desvíos."""
    produccion = produccion_por_operador_en_mes(year, month)
    analisis = analisis_promedios_por_operador_en_mes(year, month)
    prod_by_op = _produccion_lookup(produccion)

    all_ops: set[str] = set(prod_by_op) | set(analisis)
    operadores: list[dict[str, Any]] = []
    for op in sorted(all_ops, key=lambda s: s.lower()):
        prod = prod_by_op.get(op)
        bloques = analisis.get(op, [])
        total_desvios = sum(b.get("total_desvios", 0) for b in bloques)
        operadores.append(
            {
                "operador": op,
                "produccion_liters": prod["produccion_liters"] if prod else None,
                "produccion_display": prod["produccion_display"] if prod else "—",
                "turnos": prod["turnos"] if prod else 0,
                "promedio_por_turno_display": prod["promedio_por_turno_display"] if prod else "—",
                "analisis": bloques,
                "total_desvios": total_desvios,
            }
        )

    return {
        "year": year,
        "month": month,
        "label": _month_label(year, month),
        "produccion": produccion,
        "operadores": operadores,
    }


def build_inicio_reporte_context() -> dict[str, Any]:
    """Contexto del reporte por operador en inicio (mes en curso y mes anterior)."""
    now = now_operacion_naive_local()
    cy, cm = now.year, now.month
    py, pm = _prev_month(cy, cm)
    return {
        "reporte_mes_actual": reporte_operador_mes(cy, cm),
        "reporte_mes_anterior": reporte_operador_mes(py, pm),
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
