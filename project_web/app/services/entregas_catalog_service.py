from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import (
    ChoferEntrega,
    ClienteEntrega,
    Entrega,
    LugarEntrega,
    ProductoTerminado,
)
from app.repositories.entregas_repository import entregas_repo


def productos_terminados_activos() -> list[ProductoTerminado]:
    return list(
        db.session.scalars(
            select(ProductoTerminado)
            .where(ProductoTerminado.activo.is_(True))
            .order_by(ProductoTerminado.nombre.asc())
        ).all()
    )


def clientes_activos() -> list[ClienteEntrega]:
    return list(
        db.session.scalars(
            select(ClienteEntrega).where(ClienteEntrega.activo.is_(True)).order_by(ClienteEntrega.nombre.asc())
        ).all()
    )


def lugares_activos_por_cliente(cliente_id: int) -> list[LugarEntrega]:
    return list(
        db.session.scalars(
            select(LugarEntrega)
            .where(LugarEntrega.cliente_id == int(cliente_id), LugarEntrega.activo.is_(True))
            .order_by(LugarEntrega.nombre.asc())
        ).all()
    )


def lugares_activos_todos() -> list[LugarEntrega]:
    """Todos los lugares activos (p. ej. para filtrar por cliente en el formulario sin depender solo de fetch)."""
    return list(
        db.session.scalars(
            select(LugarEntrega).where(LugarEntrega.activo.is_(True)).order_by(LugarEntrega.cliente_id.asc(), LugarEntrega.nombre.asc())
        ).all()
    )


def choferes_activos() -> list[ChoferEntrega]:
    return list(
        db.session.scalars(
            select(ChoferEntrega).where(ChoferEntrega.activo.is_(True)).order_by(ChoferEntrega.nombre.asc())
        ).all()
    )


def get_lugar_entrega_validado(lugar_id: int, cliente_id: int) -> LugarEntrega | None:
    lid = int(lugar_id)
    cid = int(cliente_id)
    row = db.session.get(LugarEntrega, lid)
    if row is None or not row.activo or int(row.cliente_id) != cid:
        return None
    return row


def get_cliente_activo(cliente_id: int) -> ClienteEntrega | None:
    row = db.session.get(ClienteEntrega, int(cliente_id))
    if row is None or not row.activo:
        return None
    return row


def get_producto_terminado_activo(pid: int) -> ProductoTerminado | None:
    row = db.session.get(ProductoTerminado, int(pid))
    if row is None or not row.activo:
        return None
    return row


def get_chofer_activo(cid: int | None) -> ChoferEntrega | None:
    if cid is None:
        return None
    row = db.session.get(ChoferEntrega, int(cid))
    if row is None or not row.activo:
        return None
    return row


def listar_entregas_con_catalogos() -> list[Entrega]:
    return entregas_repo.list_with_catalogos()
