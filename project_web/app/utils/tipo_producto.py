from __future__ import annotations

from typing import Any


def normalize_tipo_producto(tipo: Any) -> str:
    if tipo is None:
        return "Normal"
    s = str(tipo).strip()
    if not s:
        return "Normal"
    if s.lower() == "filtro":
        return "Filtro"
    return "Normal"
