from __future__ import annotations

from typing import TypedDict


class ExistenciaPorCategoriaItem(TypedDict, total=False):
    """Ítem cuando categoria=todas."""

    categoria: str
    producto: str
    stock: float
    is_stockable: bool


class ExistenciaUnaCategoriaItem(TypedDict, total=False):
    """Ítem cuando se filtra una categoría (sin repetir categoria en cada fila)."""

    producto: str
    stock: float
    is_stockable: bool


class StockExistenciasResponse(TypedDict, total=False):
    categoria: str
    items: list[ExistenciaPorCategoriaItem] | list[ExistenciaUnaCategoriaItem]


class ConsumoStockItemBase(TypedDict, total=False):
    fecha: str
    hora: str
    marca: str
    cantidad: float
    operador: str
    equipo: str
    observaciones: str


class ConsumoStockItemProducto(ConsumoStockItemBase, total=False):
    id: int


class ConsumoStockItemHistorial(ConsumoStockItemBase, total=False):
    categoria: str
    producto: str


class StockConsumosProductoResponse(TypedDict, total=False):
    categoria: str
    producto: str
    items: list[ConsumoStockItemProducto]


class StockConsumosUltimosDiasResponse(TypedDict, total=False):
    dias: int
    limit: int
    items: list[ConsumoStockItemHistorial]


class StockAlertaItem(TypedDict, total=False):
    categoria: str
    producto: str
    stock_actual: float
    stock_minimo_alerta: float
    faltante: float


class StockAlertasResponse(TypedDict, total=False):
    limit: int
    items: list[StockAlertaItem]
