"""Producción estimada de hipoclorito durante el turno en curso.

Cada electrolizador produce a un ritmo fijo (litros por turno ÷ horas del turno) mientras no tenga una parada de
planta abierta. Se calcula en continuo desde el inicio operativo del turno; no se guardan movimientos: al cierre,
el stock declarado por el operador pasa a ser la nueva base y la estimación vuelve a cero.

Para cargar camiones (y programar entregas) solo se toma un porcentaje de lo estimado (margen de seguridad).
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select

from app.extensions import db
from app.models import AppParametro, PlantStopEvent
from app.services import plant_stop_service as ps

DEFAULTS: dict[str, float] = {
    "hipo.horas_turno": 8.0,
    "hipo.margen_carga_pct": 90.0,
}
LITROS_TURNO_DEFAULT = 1500.0
# Tope de la ventana estimada: si pasan más de 24 h sin un cierre recepcionado no se sigue sumando
# (el stock declarado al cierre es el que manda; esto evita números absurdos ante un cierre olvidado).
MAX_HORAS_ESTIMACION = 24.0


def electrolizadores() -> list[int]:
    """Electrolizadores con parada de planta propia (los que el sistema sabe prender/parar)."""
    out = []
    for key in ps.CIRCUIT_LABELS:
        if key.startswith("salmuera_e"):
            try:
                out.append(int(key.rsplit("e", 1)[-1]))
            except ValueError:
                continue
    return sorted(out)


def _clave_litros(eid: int) -> str:
    return f"hipo.litros_turno.e{int(eid)}"


def get_param(clave: str, default: float) -> float:
    row = db.session.get(AppParametro, clave)
    try:
        v = float(str(row.valor).replace(",", ".")) if row is not None else default
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def config() -> dict[str, Any]:
    return {
        "horas_turno": get_param("hipo.horas_turno", DEFAULTS["hipo.horas_turno"]),
        "margen_carga_pct": get_param("hipo.margen_carga_pct", DEFAULTS["hipo.margen_carga_pct"]),
        "litros_turno": {e: get_param(_clave_litros(e), LITROS_TURNO_DEFAULT) for e in electrolizadores()},
    }


def guardar_config(form: Any, user_id: int | None) -> list[str]:
    errores: list[str] = []
    nuevos: dict[str, float] = {}

    def num(nombre: str, raw: Any, lo: float, hi: float) -> float | None:
        try:
            v = float(str(raw or "").replace(",", "."))
        except ValueError:
            v = float("nan")
        if not (math.isfinite(v) and lo <= v <= hi):
            errores.append(f"{nombre}: tiene que ser un número entre {lo:g} y {hi:g}.")
            return None
        return v

    h = num("Horas del turno", form.get("horas_turno"), 1, 24)
    m = num("Margen para carga", form.get("margen_carga_pct"), 0, 100)
    if h is not None:
        nuevos["hipo.horas_turno"] = h
    if m is not None:
        nuevos["hipo.margen_carga_pct"] = m
    for e in electrolizadores():
        v = num(f"Electrolizador {e}", form.get(f"litros_e{e}"), 0, 100000)
        if v is not None:
            nuevos[_clave_litros(e)] = v
    if errores:
        return errores
    for clave, v in nuevos.items():
        row = db.session.get(AppParametro, clave) or AppParametro(clave=clave)
        row.valor = f"{v:g}"
        row.updated_by_user_id = user_id
        db.session.add(row)
    return []


def _parse(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat((iso or "").strip()[:19])
    except ValueError:
        return None


def segundos_en_parada(circuit_key: str, desde: datetime, hasta: datetime) -> float:
    """Segundos de [desde, hasta] cubiertos por paradas del circuito (las abiertas cuentan hasta `hasta`)."""
    d_iso, h_iso = desde.isoformat(timespec="seconds"), hasta.isoformat(timespec="seconds")
    eventos = db.session.scalars(
        select(PlantStopEvent).where(
            PlantStopEvent.circuit_key == circuit_key,
            PlantStopEvent.started_at_iso <= h_iso,
            or_(PlantStopEvent.ended_at_iso.is_(None), PlantStopEvent.ended_at_iso >= d_iso),
        )
    ).all()
    tramos: list[tuple[datetime, datetime]] = []
    for ev in eventos:
        a = _parse(ev.started_at_iso)
        b = _parse(ev.ended_at_iso) if ev.ended_at_iso else hasta
        if a is None or b is None:
            continue
        a, b = max(a, desde), min(b, hasta)
        if b > a:
            tramos.append((a, b))
    # Unir tramos superpuestos para no descontar dos veces.
    total = 0.0
    fin: datetime | None = None
    for a, b in sorted(tramos):
        if fin is not None and a < fin:
            a = fin
        if b > a:
            total += (b - a).total_seconds()
            fin = b if fin is None or b > fin else fin
    return total


def estimar(desde_iso: str, hasta_iso: str | None = None) -> dict[str, Any]:
    """Litros estimados producidos entre `desde` y `hasta` (ahora si se omite), por electrolizador."""
    desde = _parse(desde_iso)
    hasta = _parse(hasta_iso) if hasta_iso else _parse(ps.now_local_iso())
    cfg = config()
    detalle: dict[int, dict[str, float]] = {}
    total = 0.0
    if desde is None or hasta is None or hasta <= desde:
        return {"litros": 0.0, "detalle": detalle, "config": cfg}
    from datetime import timedelta

    if (hasta - desde).total_seconds() > MAX_HORAS_ESTIMACION * 3600:
        hasta = desde + timedelta(hours=MAX_HORAS_ESTIMACION)
    transcurrido = (hasta - desde).total_seconds()
    for e, litros_turno in cfg["litros_turno"].items():
        parado = segundos_en_parada(ps.circuit_key_for_electrolizador(e), desde, hasta)
        en_marcha = max(0.0, transcurrido - parado)
        litros = en_marcha / 3600.0 * litros_turno / cfg["horas_turno"]
        detalle[e] = {"horas_en_marcha": en_marcha / 3600.0, "horas_paradas": parado / 3600.0, "litros": litros}
        total += litros
    return {"litros": total, "detalle": detalle, "config": cfg}
