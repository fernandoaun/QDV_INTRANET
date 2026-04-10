"""
Fecha y hora de operación en planta.

Criterio único: reloj de pared en la zona `APP_TIMEZONE` (por defecto
America/Argentina/Buenos_Aires), como ingresos de stock y cambio de turno.

Los campos `created_at_iso` en modelos legacy son strings; muchas veces son ISO **naive**
(sin zona). Tras desplegar en UTC, consumos antiguos pueden haberse guardado con hora UTC
naive: para el panel, si hace falta, definir `APP_PANEL_NAIVE_ISO_IS_UTC=1` y se reinterpretan
solo al mostrar (no altera la BD).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DEFAULT_APP_TIMEZONE = "America/Argentina/Buenos_Aires"


def operacion_tz_name() -> str:
    return (os.environ.get("APP_TIMEZONE") or DEFAULT_APP_TIMEZONE).strip() or DEFAULT_APP_TIMEZONE


def operacion_zoneinfo() -> ZoneInfo:
    try:
        return ZoneInfo(operacion_tz_name())
    except Exception:
        return ZoneInfo(DEFAULT_APP_TIMEZONE)


def now_operacion_naive_local() -> datetime:
    """datetime naive con el reloj de pared en planta (mismo criterio que `now_local()` en producción)."""
    try:
        return datetime.now(operacion_zoneinfo()).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def now_operacion_local_iso_seconds() -> str:
    """ISO local sin sufijo de zona (compatible con histórico de cambio de turno)."""
    return now_operacion_naive_local().isoformat(timespec="seconds")


def _parse_iso_datetime(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def format_iso_timestamp_for_panel(iso_s: str | None) -> str | None:
    """
    Devuelve `YYYY-MM-DD HH:MM` en hora Argentina de operación, o None si no parsea.
    """
    dt = _parse_iso_datetime(iso_s or "")
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(operacion_zoneinfo()).replace(tzinfo=None)
    else:
        env = (os.environ.get("APP_PANEL_NAIVE_ISO_IS_UTC") or "").strip().lower()
        if env in ("1", "true", "yes"):
            dt = dt.replace(tzinfo=timezone.utc).astimezone(operacion_zoneinfo()).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M")


def format_consumo_stock_panel_datetime(
    created_at_iso: str | None,
    fecha: str | None,
    hora: str | None,
) -> str:
    """
    Una sola cadena para tablas (panel, consumos): prioriza `created_at_iso` coherente;
    si no parsea, usa columnas fecha/hora del registro.
    """
    out = format_iso_timestamp_for_panel(created_at_iso)
    if out:
        return out
    f, h = (fecha or "").strip(), (hora or "").strip()
    if f and h:
        hm = h[:5] if len(h) >= 5 else h
        return f"{f} {hm}"
    return f or h or "-"
