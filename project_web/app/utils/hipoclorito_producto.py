"""
Equivalencia operativa del hipoclorito entre cambio de turno, Panel, Entregas y ledger de stock.

El nombre visible en catálogo de productos terminados (p. ej. «Hipoclorito de Sodio») y el nombre
en ingresos/consumos (p. ej. «Hipoclorito») representan el mismo producto real: un solo conjunto de
aliases normalizados (minúsculas + trim) y un único nombre canónico para movimientos en `consumos_stock`.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import func

from app.constants import (
    HIPOCLORITO_ENTREGA_ALIASES_ADICIONALES,
    HIPOCLORITO_PRODUCTO_TERMINADO_NOMBRE,
    HIPOCLORITO_STOCK_NOMBRE_PRODUCTO,
)


@lru_cache
def _aliases_lower_frozen() -> frozenset[str]:
    s: set[str] = set()
    for raw in (
        HIPOCLORITO_STOCK_NOMBRE_PRODUCTO,
        HIPOCLORITO_PRODUCTO_TERMINADO_NOMBRE,
        *HIPOCLORITO_ENTREGA_ALIASES_ADICIONALES,
    ):
        t = (raw or "").strip().lower()
        if t:
            s.add(t)
    return frozenset(s)


def aliases_entrega_lower_sorted() -> list[str]:
    """Lista estable para JSON / plantillas (comparación de `Entrega.producto` normalizado)."""
    return sorted(_aliases_lower_frozen())


def normalizar_nombre_producto_entrega(nombre: str) -> str:
    return (nombre or "").strip().lower()


def es_producto_entrega_operativo_hipoclorito(nombre_producto: str) -> bool:
    n = normalizar_nombre_producto_entrega(nombre_producto)
    return bool(n) and n in _aliases_lower_frozen()


def nombre_ledger_canonico_hipoclorito() -> str:
    """Texto único en `consumos_stock` / `ingresos_stock` para este producto operativo."""
    return (HIPOCLORITO_STOCK_NOMBRE_PRODUCTO or "").strip()


def clave_catalogo_stock_producto_terminado(stock_producto: str) -> str:
    """
    Para buscar marcas/requiere_equipo en `producto_terminado`: si el texto del catálogo PT es un alias
    de hipoclorito, usar el nombre canónico del ledger (donde suele estar el catálogo de stock).
    """
    raw = (stock_producto or "").strip()
    if es_producto_entrega_operativo_hipoclorito(raw):
        return nombre_ledger_canonico_hipoclorito()
    return raw


def entrega_columna_es_hipoclorito_operativo_sql(column) -> Any:
    """
    Predicado SQL: `lower(trim(column)) IN (aliases)` para filtrar entregas de hipoclorito
    aunque `Entrega.producto` use nombre comercial o canónico.
    """
    aliases = tuple(sorted(_aliases_lower_frozen()))
    if not aliases:
        return None
    return func.lower(func.trim(column)).in_(aliases)
