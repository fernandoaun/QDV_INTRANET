"""
Avisos operativos no bloqueantes para Control de Hipoclorito (salmuera_registros).

Los umbrales y textos se definen una sola vez en _RULES; el evaluador y el JSON
para el cliente se derivan de la misma lista.
"""
from __future__ import annotations

from typing import Any

_RULES: tuple[dict[str, Any], ...] = (
    {
        "key": "hipo_exceso_soda",
        "op": "gt",
        "limit": 9.0,
        "msg": "Aviso: exceso de soda fuera de parámetro (> 9).",
    },
    {
        "key": "sal_conc",
        "op": "lt",
        "limit": 260.0,
        "msg": "Aviso: salmuera de salida de celda por debajo de 260 g/L.",
    },
    {
        "key": "sal_ph",
        "op": "gt",
        "limit": 5.0,
        "msg": "Aviso: pH de salmuera de salida de celda por encima de 5.",
    },
    {
        "key": "declor_ph",
        "op": "gt",
        "limit": 1.9,
        "msg": "Aviso: pH de declorinación por encima de 1.9.",
    },
)


def hipoclorito_operational_warning_rules_for_js() -> list[dict[str, Any]]:
    """Reglas serializables para validación en tiempo real en el navegador."""
    return [{"key": r["key"], "op": r["op"], "limit": float(r["limit"]), "msg": r["msg"]} for r in _RULES]


def evaluate_hipoclorito_operational_warnings(
    *,
    hipo_exceso_soda: float,
    sal_conc: float,
    sal_ph: float,
    declor_ph: float,
) -> list[str]:
    """
    Devuelve los mensajes de aviso activos según los valores numéricos cargados.
    No lanza excepciones: asume valores ya convertidos a float.
    """
    vals = {
        "hipo_exceso_soda": float(hipo_exceso_soda),
        "sal_conc": float(sal_conc),
        "sal_ph": float(sal_ph),
        "declor_ph": float(declor_ph),
    }
    out: list[str] = []
    for rule in _RULES:
        key = str(rule["key"])
        v = vals[key]
        op = rule["op"]
        lim = float(rule["limit"])
        if op == "gt" and v > lim:
            out.append(str(rule["msg"]))
        elif op == "lt" and v < lim:
            out.append(str(rule["msg"]))
    return out


def append_hipoclorito_warnings_to_observaciones(observaciones: str, warnings: list[str]) -> str:
    """Concatena los avisos al final de observaciones para trazabilidad al guardado."""
    base = (observaciones or "").rstrip()
    block = "\n".join(warnings)
    if not block:
        return base
    if base:
        return f"{base}\n\n{block}"
    return block
