from __future__ import annotations

from typing import TypedDict


class EntregaCatalogoPayload(TypedDict, total=False):
    cliente_nombre: str | None
    lugar_nombre: str | None
    producto_terminado_nombre: str | None
    chofer_nombre: str | None


class EntregaListItem(TypedDict, total=False):
    """Cada elemento de GET /api/v1/entregas → items[]."""

    id: int
    estado: str
    cliente: str
    lugar_entrega: str
    producto: str
    cantidad: float
    cantidad_programada: float
    cantidad_real_cargada: float | None
    cantidad_real_entregada: float | None
    cantidad_operativa_cargada: float
    cantidad_operativa_entregada: float
    unidad: str | None
    fecha_prevista: str
    observaciones: str | None
    chofer_previsto: str | None
    cliente_id: int | None
    lugar_entrega_id: int | None
    producto_terminado_id: int | None
    chofer_entrega_id: int | None
    catalogo: EntregaCatalogoPayload
    created_at_iso: str
    updated_at_iso: str
    created_by_user_id: int | None
    cargada_at_iso: str | None
    cargada_by_user_id: int | None
    consumo_stock_id: int | None
    stock_categoria: str | None
    stock_marca: str | None
    stock_equipo_id: int | None
    entregada_at_iso: str | None
    entregada_by_user_id: int | None
    entregada_chofer_nombre: str | None
    entregada_lugar: str | None
    entregada_dia_semana: str | None


class EntregaListResponse(TypedDict):
    items: list[EntregaListItem]
