from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from app.extensions import db
from app.constants import ENTREGAS_MARCA_PRODUCTO_TERMINADO_TRAZA, ENTREGAS_STOCK_CATEGORIA
from app.models import Entrega, EntregaEvento, User
from app.services import operational_informed_stock as informed_stock
from app.services import stock_service
from app.utils.hipoclorito_producto import nombre_ledger_canonico_hipoclorito

_DIAS_ES = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


def dia_semana_es(fecha_hora: datetime) -> str:
    return _DIAS_ES[int(fecha_hora.weekday())]


def append_evento(
    entrega_id: int,
    tipo: str,
    at_iso: str,
    actor: User | None,
    actor_display: str,
    detalle: dict[str, Any] | None = None,
) -> None:
    db.session.add(
        EntregaEvento(
            entrega_id=int(entrega_id),
            tipo=(tipo or "").strip()[:32],
            at_iso=at_iso,
            actor_user_id=int(actor.id) if actor else None,
            actor_display=(actor_display or "").strip() or "sistema",
            detalle=json.dumps(detalle, ensure_ascii=False) if detalle else None,
        )
    )


def puede_editar_campos_completos(entrega: Entrega) -> bool:
    return str(entrega.estado or "") == "programada"


def puede_editar_logistica_tras_carga(entrega: Entrega) -> bool:
    return str(entrega.estado or "") == "cargada"


def puede_marcar_cargada(entrega: Entrega) -> bool:
    return str(entrega.estado or "") == "programada" and entrega.consumo_stock_id is None


def validar_hipochlorito_cantidad_vs_stock_operativo_panel(
    cantidad: float,
    *,
    exclude_entrega_id: int | None = None,
) -> None:
    """Delega en la fuente única de stock informado (misma que el Panel)."""
    informed_stock.raise_if_programada_qty_exceeds_operational_avail(
        cantidad, exclude_entrega_id=exclude_entrega_id
    )


def puede_marcar_entregada(entrega: Entrega) -> bool:
    if str(entrega.estado or "") == "entregada":
        return False
    if stock_service.producto_entrega_es_stock_hipoclorito(str(entrega.producto or "")):
        return str(entrega.estado or "") == "cargada"
    return str(entrega.estado or "") in ("programada", "cargada")


def ejecutar_cargada(entrega: Entrega, actor: User | None, ahora: datetime) -> None:
    if not puede_marcar_cargada(entrega):
        raise ValueError("Esta entrega no admite la acción «Cargar».")
    op_name = _actor_operador(actor)
    iso = ahora.isoformat(timespec="seconds")
    consumo_id: int | None = None
    if stock_service.producto_entrega_es_stock_hipoclorito(str(entrega.producto or "")):
        cat = (entrega.stock_categoria or ENTREGAS_STOCK_CATEGORIA).strip()
        if cat != ENTREGAS_STOCK_CATEGORIA:
            raise ValueError("La categoría de stock de la entrega debe ser producto terminado.")
        marca = (ENTREGAS_MARCA_PRODUCTO_TERMINADO_TRAZA or "").strip()
        if not marca:
            raise ValueError("Marca de trazabilidad QDV no configurada (constante ENTREGAS_MARCA_PRODUCTO_TERMINADO_TRAZA).")
        entrega.stock_marca = marca
        qty = float(entrega.cantidad or 0)
        informed_stock.raise_if_carga_qty_exceeds_instant(qty)
        obs = f"Entrega #{entrega.id} · carga en camión"
        # Un solo nombre en el ledger aunque `Entrega.producto` use el alias comercial del PT.
        prod_ledger = nombre_ledger_canonico_hipoclorito()
        rec = stock_service.add_consumo_stock_record(
            cat,
            prod_ledger,
            marca,
            qty,
            op_name,
            observaciones=obs,
            equipo_id=int(entrega.stock_equipo_id) if entrega.stock_equipo_id else None,
            fecha_hora=ahora,
            skip_ledger_availability_check=True,
        )
        db.session.flush()
        consumo_id = int(rec.id)
    entrega.estado = "cargada"
    entrega.cargada_at_iso = iso
    entrega.cargada_by_user_id = int(actor.id) if actor else None
    entrega.updated_at_iso = iso
    if consumo_id is not None:
        entrega.consumo_stock_id = consumo_id
    detalle_carga: dict[str, Any] = {"consumo_stock_id": consumo_id, "operador_stock": op_name}
    if consumo_id is not None:
        detalle_carga["producto_entrega"] = str(entrega.producto or "").strip() or None
        detalle_carga["producto_ledger"] = nombre_ledger_canonico_hipoclorito()
    append_evento(
        int(entrega.id),
        "cargada",
        iso,
        actor,
        _actor_display(actor),
        detalle_carga,
    )


def ejecutar_entregada(entrega: Entrega, actor: User | None, ahora: datetime) -> None:
    if not puede_marcar_entregada(entrega):
        raise ValueError("Esta entrega no admite la acción «Entregado».")
    iso = ahora.isoformat(timespec="seconds")
    lugar = (entrega.lugar_entrega or "").strip()
    chof = _actor_display(actor)
    entrega.estado = "entregada"
    entrega.entregada_at_iso = iso
    entrega.entregada_by_user_id = int(actor.id) if actor else None
    entrega.entregada_chofer_nombre = chof
    entrega.entregada_lugar = lugar
    entrega.entregada_dia_semana = dia_semana_es(ahora)
    entrega.updated_at_iso = iso
    append_evento(
        int(entrega.id),
        "entregada",
        iso,
        actor,
        chof,
        {
            "lugar_entrega": lugar,
            "fecha": ahora.strftime("%Y-%m-%d"),
            "hora": ahora.strftime("%H:%M"),
            "dia_semana": entrega.entregada_dia_semana,
            "responsable": chof,
        },
    )


def _actor_display(u: User | None) -> str:
    if u is None:
        return "sistema"
    full = (getattr(u, "nombre_completo", None) or "").strip()
    if full:
        return full
    return (u.username or "").strip() or "usuario"


def _actor_operador(u: User | None) -> str:
    return _actor_display(u)


def listar_entregas() -> list[Entrega]:
    from app.services import entregas_catalog_service

    return entregas_catalog_service.listar_entregas_con_catalogos()


def entrega_to_api_dict(e: Entrega) -> dict[str, Any]:
    """Forma estable para API / clientes offline (mismos datos que ve gestión web)."""
    cr = e.cliente_row
    lr = e.lugar_row
    pt = e.producto_terminado
    ch = e.chofer_row

    def _opt_int(v: int | None) -> int | None:
        return int(v) if v is not None else None

    return {
        "id": int(e.id),
        "estado": str(e.estado or ""),
        "cliente": str(e.cliente or ""),
        "lugar_entrega": str(e.lugar_entrega or ""),
        "producto": str(e.producto or ""),
        "cantidad": float(e.cantidad or 0),
        "unidad": ((e.unidad or "").strip() or None),
        "fecha_prevista": str(e.fecha_prevista or ""),
        "observaciones": ((e.observaciones or "").strip() or None),
        "chofer_previsto": ((e.chofer_previsto or "").strip() or None),
        "cliente_id": _opt_int(e.cliente_id),
        "lugar_entrega_id": _opt_int(e.lugar_entrega_id),
        "producto_terminado_id": _opt_int(e.producto_terminado_id),
        "chofer_entrega_id": _opt_int(e.chofer_entrega_id),
        "catalogo": {
            "cliente_nombre": (cr.nombre if cr else None),
            "lugar_nombre": (lr.nombre if lr else None),
            "producto_terminado_nombre": (pt.nombre if pt else None),
            "chofer_nombre": (ch.nombre if ch else None),
        },
        "created_at_iso": e.created_at_iso,
        "updated_at_iso": e.updated_at_iso,
        "created_by_user_id": _opt_int(e.created_by_user_id),
        "cargada_at_iso": e.cargada_at_iso,
        "cargada_by_user_id": _opt_int(e.cargada_by_user_id),
        "consumo_stock_id": _opt_int(e.consumo_stock_id),
        "stock_categoria": e.stock_categoria,
        "stock_marca": e.stock_marca,
        "stock_equipo_id": _opt_int(e.stock_equipo_id),
        "entregada_at_iso": e.entregada_at_iso,
        "entregada_by_user_id": _opt_int(e.entregada_by_user_id),
        "entregada_chofer_nombre": e.entregada_chofer_nombre,
        "entregada_lugar": e.entregada_lugar,
        "entregada_dia_semana": e.entregada_dia_semana,
    }
