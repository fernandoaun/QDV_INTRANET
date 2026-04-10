from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    AguaRegistro,
    ConsumoStock,
    Equipo,
    ProductoColor,
    ReactorRegistro,
    SalmueraRegistro,
)
from app.web.modules.produccion.operativa_context import now_local

HIPO_OPTIONS: list[dict[str, str]] = [
    {"key": "hipo_conc", "label": "Hipo conc"},
    {"key": "amperaje", "label": "Amperaje"},
    {"key": "voltaje_total", "label": "Voltaje total"},
    {"key": "caudal_agua_l_h", "label": "Caudal agua (L/h)"},
    {"key": "caudal_salmuera_l_h", "label": "Caudal salmuera (L/h)"},
    {"key": "hipo_exceso_soda", "label": "Exceso soda"},
    {"key": "sal_temp", "label": "Temperatura salmuera"},
    {"key": "sal_conc", "label": "Concentración salmuera"},
    {"key": "sal_ph", "label": "pH salmuera"},
]

SALMUERA_OPTIONS: list[dict[str, str]] = [
    {"key": "concentracion_tabla", "label": "Concentración salmuera"},
    {"key": "exceso_naoh", "label": "Exceso soda"},
    {"key": "exceso_na2co3", "label": "Exceso carbonato sodio"},
    {"key": "ph", "label": "pH"},
    {"key": "temperatura", "label": "Temperatura"},
    {"key": "densidad", "label": "Densidad"},
]

AGUA_OPTIONS: list[dict[str, str]] = [
    {"key": "dureza", "label": "Dureza"},
    {"key": "temperatura", "label": "Temperatura"},
    {"key": "numero_columna", "label": "Número de columna"},
]

_PALETTE = (
    "#2f80ed",
    "#27ae60",
    "#f2994a",
    "#9b51e0",
    "#eb5757",
    "#00a8c6",
    "#6fcf97",
    "#f2c94c",
    "#56ccf2",
    "#bb6bd9",
)

_CHART_PALETTE = ["#2f80ed", "#27ae60", "#f2994a", "#9b51e0"]


def _distinct_electrolizadores_salmuera() -> list[int]:
    """Electrolizadores que aparecen en registros de control hipoclorito (salmuera fusión), ordenados."""
    rows = db.session.scalars(
        select(SalmueraRegistro.electrolizador)
        .where(SalmueraRegistro.electrolizador > 0)
        .distinct()
        .order_by(SalmueraRegistro.electrolizador.asc())
    ).all()
    return [int(x) for x in rows]


def _parse_hipo_electrolizador_param(raw: str | None) -> tuple[str, int | None]:
    """
    Valor normalizado para URLs y filtro SQL.
    Retorna (valor_en_query, id_electrolizador o None = todos).
    """
    s = (raw or "").strip().lower()
    if not s or s in ("all", "todos", "*"):
        return "all", None
    if s.isdigit():
        n = int(s)
        if n > 0:
            return str(n), n
    return "all", None


def _parse_vars_selection(
    raw_list: list[str],
    raw_csv: str | None,
    allowed: set[str],
    defaults: list[str],
    max_n: int = 4,
) -> list[str]:
    vals = [str(v).strip() for v in raw_list if str(v).strip()]
    if not vals and raw_csv:
        vals = [v.strip() for v in raw_csv.split(",") if v.strip()]
    clean: list[str] = []
    for v in vals:
        if v in allowed and v not in clean:
            clean.append(v)
        if len(clean) >= max_n:
            break
    if clean:
        return clean
    return [d for d in defaults if d in allowed][:max_n]


def _ts_pretty(fecha_iso: str, hora_hm: str, created_at_iso: str) -> str:
    f = (fecha_iso or "").strip()
    h = (hora_hm or "").strip()
    if f and h:
        return f"{f} {h}"
    if f:
        return f
    return (created_at_iso or "")[:16].replace("T", " ")


def _color_for_producto(
    prod: str,
    color_by_key: dict[str, str],
    palette: tuple[str, ...] = _PALETTE,
) -> str:
    key = (prod or "").strip().lower()
    if not key:
        return "#9aa5b1"
    if key in color_by_key and color_by_key[key]:
        return color_by_key[key]
    idx = sum(ord(ch) for ch in key) % len(palette)
    return palette[idx]


def _build_chart_payload(
    rows_in: list[Any],
    selected_keys: list[str],
    options: list[dict[str, str]],
) -> dict[str, Any]:
    label_by_key = {o["key"]: o["label"] for o in options}
    labels: list[str] = []
    for r in rows_in:
        labels.append(_ts_pretty(str(r.fecha_iso), str(r.hora_hm), str(r.created_at_iso)))
    datasets: list[dict[str, Any]] = []
    axes: list[dict[str, Any]] = []
    for i, key in enumerate(selected_keys):
        y_axis_id = "y" if i == 0 else f"y{i+1}"
        vals: list[float | None] = []
        has_any = False
        for r in rows_in:
            raw = getattr(r, key, None)
            if raw is None:
                vals.append(None)
                continue
            try:
                num = float(raw)
                vals.append(num)
                has_any = True
            except (TypeError, ValueError):
                vals.append(None)
        if not has_any:
            continue
        datasets.append(
            {
                "label": label_by_key.get(key, key),
                "data": vals,
                "borderColor": _CHART_PALETTE[i % len(_CHART_PALETTE)],
                "yAxisID": y_axis_id,
            }
        )
        axes.append(
            {
                "id": y_axis_id,
                "position": "left" if i % 2 == 0 else "right",
                "displayGrid": i == 0,
            }
        )
    return {"labels": labels, "datasets": datasets, "axes": axes}


def build_graficos_template_context(
    *,
    desde: str,
    dia_arg: str,
    hipo_vars: list[str],
    hipo_vars_csv: str | None,
    hipo_electrolizador: str | None,
    salmuera_vars: list[str],
    salmuera_vars_csv: str | None,
    agua_vars: list[str],
    agua_vars_csv: str | None,
) -> dict[str, Any]:
    """
    Datos para ``produccion/graficos.html``: series, calendario de consumos y payloads Chart.js.
    """
    rows = db.session.execute(
        select(SalmueraRegistro.fecha_iso, func.count(SalmueraRegistro.id))
        .where(SalmueraRegistro.fecha_iso >= desde)
        .group_by(SalmueraRegistro.fecha_iso)
        .order_by(SalmueraRegistro.fecha_iso)
    ).all()

    hoy = now_local().date()
    inicio_30d = hoy - timedelta(days=29)
    inicio_iso = inicio_30d.strftime("%Y-%m-%d")
    fin_iso = hoy.strftime("%Y-%m-%d")
    consumo_rows = db.session.execute(
        select(ConsumoStock, Equipo.nombre_equipo)
        .outerjoin(Equipo, ConsumoStock.equipo_id == Equipo.id)
        .where(ConsumoStock.fecha >= inicio_iso, ConsumoStock.fecha <= fin_iso)
        .order_by(ConsumoStock.fecha.desc(), ConsumoStock.hora.desc(), ConsumoStock.id.desc())
    ).all()

    productos_keys = sorted(
        {str(r[0].producto).strip().lower() for r in consumo_rows if str(r[0].producto or "").strip()}
    )
    color_rows = (
        db.session.scalars(select(ProductoColor).where(ProductoColor.nombre_clave.in_(productos_keys))).all()
        if productos_keys
        else []
    )
    color_by_key = {str(c.nombre_clave).strip().lower(): str(c.color_hex) for c in color_rows}

    consumos_por_dia: dict[str, list[dict[str, Any]]] = {}
    for consumo, eq_name in consumo_rows:
        fecha = str(consumo.fecha)
        item = {
            "fecha": fecha,
            "hora": consumo.hora,
            "producto": consumo.producto,
            "cantidad": consumo.cantidad,
            "unidad": "",
            "equipo": (eq_name or ""),
            "operador": consumo.operador,
            "observaciones": consumo.observaciones or "",
            "color": _color_for_producto(str(consumo.producto), color_by_key),
        }
        consumos_por_dia.setdefault(fecha, []).append(item)

    dia_sel = dia_arg.strip()
    if not dia_sel or dia_sel < inicio_iso or dia_sel > fin_iso:
        dia_sel = fin_iso
    detalle_dia = consumos_por_dia.get(dia_sel, [])

    dias_30d = [inicio_30d + timedelta(days=i) for i in range(30)]
    celdas: list[dict[str, Any]] = []
    for _ in range(dias_30d[0].weekday()):
        celdas.append({"blank": True})
    for d in dias_30d:
        f_iso = d.strftime("%Y-%m-%d")
        items = consumos_por_dia.get(f_iso, [])
        unique_colors: list[str] = []
        for it in items:
            c = str(it["color"])
            if c not in unique_colors:
                unique_colors.append(c)
        celdas.append(
            {
                "blank": False,
                "fecha_iso": f_iso,
                "dia_num": d.day,
                "is_today": f_iso == fin_iso,
                "is_selected": f_iso == dia_sel,
                "dots": unique_colors[:5],
                "extra": max(len(unique_colors) - 5, 0),
                "n_consumos": len(items),
            }
        )
    while len(celdas) % 7 != 0:
        celdas.append({"blank": True})

    hipo_allowed = {o["key"] for o in HIPO_OPTIONS}
    sal_allowed = {o["key"] for o in SALMUERA_OPTIONS}
    agua_allowed = {o["key"] for o in AGUA_OPTIONS}

    hipo_selected = _parse_vars_selection(hipo_vars, hipo_vars_csv, hipo_allowed, ["hipo_conc"])
    salmuera_selected = _parse_vars_selection(salmuera_vars, salmuera_vars_csv, sal_allowed, ["concentracion_tabla"])
    agua_selected = _parse_vars_selection(agua_vars, agua_vars_csv, agua_allowed, ["dureza"])

    hipo_electrolizador_sel, hipo_electrolizador_id = _parse_hipo_electrolizador_param(hipo_electrolizador)
    elect_ids = _distinct_electrolizadores_salmuera()
    ids_for_select = sorted(
        set(elect_ids) | ({int(hipo_electrolizador_id)} if hipo_electrolizador_id is not None else set())
    )
    hipo_electrolizador_opciones: list[dict[str, str]] = [{"value": "all", "label": "Todos"}] + [
        {"value": str(eid), "label": f"Electrolizador {eid}"} for eid in ids_for_select
    ]

    cutoff_dt = now_local() - timedelta(hours=24)
    cutoff_iso = cutoff_dt.isoformat(timespec="seconds")

    hipo_stmt = (
        select(SalmueraRegistro)
        .where(SalmueraRegistro.created_at_iso >= cutoff_iso)
        .order_by(SalmueraRegistro.created_at_iso.asc(), SalmueraRegistro.id.asc())
        .limit(2000)
    )
    if hipo_electrolizador_id is not None:
        hipo_stmt = hipo_stmt.where(SalmueraRegistro.electrolizador == int(hipo_electrolizador_id))
    hipo_rows = db.session.scalars(hipo_stmt).all()
    salmuera_rows = db.session.scalars(
        select(ReactorRegistro)
        .where(ReactorRegistro.created_at_iso >= cutoff_iso)
        .order_by(ReactorRegistro.created_at_iso.asc(), ReactorRegistro.id.asc())
        .limit(2000)
    ).all()
    agua_rows = db.session.scalars(
        select(AguaRegistro)
        .where(AguaRegistro.created_at_iso >= cutoff_iso)
        .order_by(AguaRegistro.created_at_iso.asc(), AguaRegistro.id.asc())
        .limit(2000)
    ).all()

    hipo_chart = _build_chart_payload(hipo_rows, hipo_selected, HIPO_OPTIONS)
    salmuera_chart = _build_chart_payload(salmuera_rows, salmuera_selected, SALMUERA_OPTIONS)
    agua_chart = _build_chart_payload(agua_rows, agua_selected, AGUA_OPTIONS)

    hipo_sin_datos_electrolizador = bool(hipo_electrolizador_id is not None and not hipo_rows)

    return {
        "desde": desde,
        "serie": [{"fecha": r[0], "n": r[1]} for r in rows],
        "calendario_celdas": celdas,
        "calendario_dia_sel": dia_sel,
        "detalle_dia": detalle_dia,
        "inicio_30d_iso": inicio_iso,
        "fin_30d_iso": fin_iso,
        "hipo_selected": hipo_selected,
        "salmuera_selected": salmuera_selected,
        "agua_selected": agua_selected,
        "hipo_csv": ",".join(hipo_selected),
        "salmuera_csv": ",".join(salmuera_selected),
        "agua_csv": ",".join(agua_selected),
        "hipo_options": HIPO_OPTIONS,
        "salmuera_options": SALMUERA_OPTIONS,
        "agua_options": AGUA_OPTIONS,
        "hipo_chart": hipo_chart,
        "salmuera_chart": salmuera_chart,
        "agua_chart": agua_chart,
        "cutoff_24h_iso": cutoff_iso,
        "hipo_electrolizador_sel": hipo_electrolizador_sel,
        "hipo_electrolizador_opciones": hipo_electrolizador_opciones,
        "hipo_sin_datos_electrolizador": hipo_sin_datos_electrolizador,
    }
