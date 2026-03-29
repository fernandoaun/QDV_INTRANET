from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import func, select

from app.extensions import db
from app.models import ConsumoStock, Equipo, IngresoStock, ProductoCatalogo
from app.utils.tipo_producto import normalize_tipo_producto


def _validate_cat(cat: str) -> str:
    c = (cat or "").strip().lower()
    if c not in ("materia_prima", "laboratorio"):
        raise ValueError("Categoría inválida.")
    return c


def productos_catalogo(cat: str) -> list[str]:
    c = _validate_cat(cat)
    rows = db.session.scalars(
        select(ProductoCatalogo.nombre_producto)
        .where(ProductoCatalogo.categoria == c, ProductoCatalogo.activo.is_(True))
        .order_by(ProductoCatalogo.nombre_producto)
    ).all()
    return [str(x) for x in rows]


def ensure_producto(cat: str, nombre: str, tipo: str = "Normal") -> None:
    c = _validate_cat(cat)
    n = (nombre or "").strip()
    if not n:
        raise ValueError("Producto vacío.")
    t = normalize_tipo_producto(tipo)
    now = datetime.now().isoformat(timespec="seconds")
    row = db.session.execute(
        select(ProductoCatalogo).where(
            ProductoCatalogo.categoria == c,
            ProductoCatalogo.nombre_producto == n,
        )
    ).scalar_one_or_none()
    if row:
        row.activo = True
        row.tipo_producto = t
    else:
        db.session.add(
            ProductoCatalogo(
                categoria=c,
                nombre_producto=n,
                tipo_producto=t,
                activo=True,
                created_at_iso=now,
            )
        )


def is_filter_product(cat: str, nombre: str) -> bool:
    c = _validate_cat(cat)
    key = (nombre or "").strip().lower()
    if not key:
        return False
    row = db.session.execute(
        select(ProductoCatalogo).where(
            ProductoCatalogo.categoria == c,
            func.lower(func.trim(ProductoCatalogo.nombre_producto)) == key,
            ProductoCatalogo.activo.is_(True),
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    return normalize_tipo_producto(row.tipo_producto) == "Filtro"


def stock_actual(cat: str, producto: str, marca: str) -> float:
    c = _validate_cat(cat)
    p = (producto or "").strip()
    m = (marca or "").strip()
    ing = db.session.scalar(
        select(func.coalesce(func.sum(IngresoStock.cantidad), 0.0)).where(
            IngresoStock.categoria == c,
            IngresoStock.producto == p,
            IngresoStock.marca == m,
        )
    )
    cons = db.session.scalar(
        select(func.coalesce(func.sum(ConsumoStock.cantidad), 0.0)).where(
            ConsumoStock.categoria == c,
            ConsumoStock.producto == p,
            ConsumoStock.marca == m,
        )
    )
    return max(float(ing or 0) - float(cons or 0), 0.0)


def marcas_con_stock(cat: str, producto: str) -> list[str]:
    c = _validate_cat(cat)
    p = (producto or "").strip()
    rows = db.session.execute(
        select(IngresoStock.marca)
        .where(IngresoStock.categoria == c, IngresoStock.producto == p)
        .group_by(IngresoStock.marca)
        .order_by(IngresoStock.marca)
    ).all()
    out: list[str] = []
    for (marca,) in rows:
        if stock_actual(c, p, str(marca)) > 0:
            out.append(str(marca))
    return out


def equipos_activos() -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(Equipo).where(Equipo.activo.is_(True)).order_by(Equipo.nombre_equipo)
    ).all()
    return [{"id": r.id, "nombre_equipo": r.nombre_equipo} for r in rows]


def save_ingreso(
    categoria: str,
    producto: str,
    marca: str,
    vencimiento: str,
    lote: str,
    cantidad: float,
    operador: str,
) -> None:
    c = _validate_cat(categoria)
    p = (producto or "").strip()
    m = (marca or "").strip()
    v = (vencimiento or "").strip()
    l = (lote or "").strip()
    op = (operador or "").strip() or "sistema"
    qty = float(cantidad)
    if not p or not m or not v or not l:
        raise ValueError("Completá producto, marca, vencimiento y lote.")
    if qty <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")
    ensure_producto(c, p)
    now = datetime.now()
    db.session.add(
        IngresoStock(
            categoria=c,
            producto=p,
            marca=m,
            vencimiento=v,
            lote=l,
            cantidad=qty,
            fecha=now.strftime("%Y-%m-%d"),
            hora=now.strftime("%H:%M"),
            operador=op,
            created_at_iso=now.isoformat(timespec="seconds"),
        )
    )
    db.session.commit()


def save_consumo(
    categoria: str,
    producto: str,
    marca: str,
    cantidad: float,
    operador: str,
    observaciones: str = "",
    equipo_id: Optional[int] = None,
) -> None:
    c = _validate_cat(categoria)
    p = (producto or "").strip()
    m = (marca or "").strip()
    op = (operador or "").strip() or "sistema"
    qty = float(cantidad)
    if not p or not m:
        raise ValueError("Producto y marca obligatorios.")
    if qty <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")
    st = stock_actual(c, p, m)
    if st <= 0:
        raise ValueError("No hay stock disponible.")
    if qty > st:
        raise ValueError("No podés consumir más de lo disponible.")

    eq_sql: Optional[int] = None
    if is_filter_product(c, p):
        if equipo_id is None:
            raise ValueError("Para producto tipo filtro tenés que elegir equipo.")
        eid = int(equipo_id)
        row = db.session.get(Equipo, eid)
        if row is None or not row.activo:
            raise ValueError("Equipo inválido o inactivo.")
        eq_sql = eid
    now = datetime.now()
    db.session.add(
        ConsumoStock(
            categoria=c,
            producto=p,
            marca=m,
            cantidad=qty,
            fecha=now.strftime("%Y-%m-%d"),
            hora=now.strftime("%H:%M"),
            operador=op,
            observaciones=(observaciones or "").strip(),
            equipo_id=eq_sql,
            created_at_iso=now.isoformat(timespec="seconds"),
        )
    )
    db.session.commit()


def stock_consolidado(cat: str) -> list[dict[str, Any]]:
    c = _validate_cat(cat)
    ing = {
        str(r[0]): float(r[1] or 0)
        for r in db.session.execute(
            select(IngresoStock.producto, func.sum(IngresoStock.cantidad))
            .where(IngresoStock.categoria == c)
            .group_by(IngresoStock.producto)
        ).all()
    }
    con = {
        str(r[0]): float(r[1] or 0)
        for r in db.session.execute(
            select(ConsumoStock.producto, func.sum(ConsumoStock.cantidad))
            .where(ConsumoStock.categoria == c)
            .group_by(ConsumoStock.producto)
        ).all()
    }
    keys = set(ing) | set(con)
    out: list[dict[str, Any]] = []
    for prod in sorted(keys, key=lambda x: str(x).lower()):
        s = float(ing.get(prod, 0) or 0) - float(con.get(prod, 0) or 0)
        if s > 0:
            out.append({"producto": str(prod), "stock": s})
    return out
