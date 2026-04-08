from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

def validate_float(text: str) -> bool:
    """Permite vacío, o float con punto. Bloquea coma."""
    if text == "":
        return True
    if "," in text:
        return False
    try:
        float(text)
        return True
    except Exception:
        return False

def validate_int(text: str) -> bool:
    """Permite vacío, o int. Bloquea coma y punto."""
    if text == "":
        return True
    if "," in text or "." in text:
        return False
    try:
        int(text)
        return True
    except Exception:
        return False

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def is_int_ok(value: str) -> bool:
    """
    Devuelve True si el string es un entero válido (no vacío).
    """
    try:
        if value is None:
            return False
        value = value.strip()
        if value == "":
            return False
        int(value)
        return True
    except ValueError:
        return False

def is_float_ok(value: str) -> bool:
    """
    Devuelve True si el string es un número válido (float) y no está vacío.
    Acepta coma o punto como separador decimal.
    """
    try:
        if value is None:
            return False
        value = value.strip()
        if value == "":
            return False
        value = value.replace(",", ".")
        float(value)
        return True
    except ValueError:
        return False

def fmt_num(value, decimals: int = 2) -> str:
    """
    Formatea un número para mostrar en tablas.
    - None / "" -> ""
    - float/int -> string con decimales
    """
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return ""
            value = value.replace(",", ".")
        num = float(value)
        fmt = f"{{:.{decimals}f}}"
        return fmt.format(num)
    except Exception:
        return ""


def to_float_or_none(x: Any) -> Optional[float]:
    """Conversión segura a float para gráficos y series (None si no es convertible)."""
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None

