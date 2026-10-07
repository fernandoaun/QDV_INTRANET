"""Fechas para mostrar: siempre día/mes/año (dd/mm/aaaa), con hora HH:MM si la hay.

En la base y en los formularios las fechas siguen en ISO (aaaa-mm-dd); esto es solo presentación.
Las pantallas se convierten en el navegador con `static/js/fechas_ar.js` (misma expresión regular);
acá se usa para lo que no pasa por el navegador: mails, etiquetas de gráficos y el filtro `fecha`.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# aaaa-mm-dd, opcionalmente con hora (T o espacio), segundos, fracción y zona horaria.
ISO_FECHA_RE = re.compile(
    r"(?<![\w/-])(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?"
    r"(?![\w-])"
)


def _reemplazo(m: re.Match[str]) -> str:
    y, mo, d, hh, mm = m.groups()
    if not (1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
        return m.group(0)
    out = f"{d}/{mo}/{y}"
    return f"{out} {hh}:{mm}" if hh is not None else out


def fechas_ar_en_texto(texto: str | None) -> str:
    """Reemplaza cada fecha ISO dentro de un texto por dd/mm/aaaa (y HH:MM si tenía hora)."""
    if not texto:
        return texto or ""
    return ISO_FECHA_RE.sub(_reemplazo, texto)


def fecha_ar(value: Any, con_hora: bool | None = None) -> str:
    """date → dd/mm/aaaa; datetime → dd/mm/aaaa HH:MM; texto ISO → igual. Vacío → ''."""
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M" if con_hora is not False else "%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    s = fechas_ar_en_texto(str(value))
    if con_hora is False:
        return s[:10]
    return s
