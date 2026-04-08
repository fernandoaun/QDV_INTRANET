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
    "raise_if_programada_qty_exceeds_operational_avail",
    "raise_if_carga_qty_exceeds_instant",
]


def raise_if_programada_qty_exceeds_operational_avail(
    cantidad: float,
    *,
    exclude_entrega_id: int | None = None,
) -> None:
    """
    Impide programar más litros que el instantáneo menos lo ya comprometido en otras «programada».
    Misma base numérica que el KPI de stock del Panel.
    """
    qty = float(cantidad)
    avail = operational_liters_available_for_new_programada(exclude_entrega_id)
    if avail is None:
        raise ValueError(
            "No hay stock operativo informado para hipoclorito: se requiere un cambio de turno "
            "recepcionado con stock válido (criterio del Panel)."
        )
    if qty > float(avail) + 1e-6:
        disp = format_header_liters(float(avail))
        raise ValueError(
            "El volumen supera lo disponible para programar según el stock operativo del Panel "
            f"(queda {disp} considerando otras entregas ya programadas)."
        )


def raise_if_carga_qty_exceeds_instant(cantidad: float) -> None:
    """
    Al marcar «Cargar», el volumen no puede superar el stock instantáneo (antes de registrar el consumo
    en el ledger). Ese instantáneo es el mismo valor que muestra el Panel.
    """
    qty = float(cantidad)
    instant = get_instant_stock()
    if instant is None:
        raise ValueError(
            "No hay stock operativo informado: se requiere un cambio de turno recepcionado "
            "con stock de hipoclorito válido (mismo criterio que el Panel)."
        )
    if qty > float(instant) + 1e-6:
        disp = format_header_liters(float(instant))
        raise ValueError(
            "La cantidad supera el stock instantáneo operativo (mismo valor que el Panel). "
            f"Disponible antes de este camión: {disp}."
        )
