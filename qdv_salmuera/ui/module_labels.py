from __future__ import annotations

MODULE_NAMES = {
    "salmuera": "CONTROL HIPOCLORITO",
    "reactor": "CIRCUITO DE SALMUERA",
    "agua": "CIRCUITO DE AGUA",
}


def module_label(module_key: str, default: str = "") -> str:
    return MODULE_NAMES.get(module_key, default or module_key)
