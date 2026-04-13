"""
Stock informado operativo de hipoclorito (litros): fuente única de aplicación para Panel y Entregas.

La implementación vive en `shift_hypochlorite_indicators_service`; este módulo es el punto de entrada
público para rutas, plantillas y servicios, y concentra validaciones de negocio ligadas a ese stock.
"""
from __future__ import annotations

from app.services.shift_hypochlorite_indicators_service import (
    format_header_liters,
    get_instant_stock,
    get_last_shift_production,
    header_operational_indicators_dict,
    operational_liters_available_for_new_programada,
    sum_hipochlorito_programada_liters,
)

__all__ = [
    "format_header_liters",
    "get_instant_stock",
    "get_last_shift_production",
    "header_operational_indicators_dict",
    "operational_liters_available_for_new_programada",
    "sum_hipochlorito_programada_liters",
    "raise_if_carga_qty_exceeds_instant",
]


def raise_if_carga_qty_exceeds_instant(cantidad: float) -> None:
    """
    Al marcar «Cargar», el volumen no puede superar el stock instantáneo (antes de registrar el consumo
    en el ledger). Ese instantáneo es el mismo valor que muestra el Panel.
    """
    qty = float(cantidad)
    instant = get_instant_stock()
    if instant is None:
        raise ValueError(
            "No hay stock operativo informado en planta para validar la carga. "
            "Recepcioná un cambio de turno con stock de hipoclorito válido (mismo criterio que el Panel) e intentá de nuevo."
        )
    if qty > float(instant) + 1e-6:
        disp = format_header_liters(float(instant))
        raise ValueError(
            "No hay stock suficiente en planta para realizar la carga. "
            f"Disponible según el stock operativo del Panel antes de este camión: {disp}."
        )
