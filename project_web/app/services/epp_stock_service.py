"""Stock de ropa y EPP (lo lleva la responsable de laboratorio).

Saldo = suma de movimientos por ítem (y por talle en los ítems con `stock_por_talle`):
- ingreso: compras (+)
- entrega: cada entrega registrada en Personal descuenta sola (−); si no hay stock se registra igual y se avisa
- ajuste: diferencia de un conteo físico (±); el conteo inicial arranca el stock

Las entregas registradas antes de empezar a llevar el stock no descuentan.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import PersonalEntregaEpp, PersonalEppItem, PersonalEppMovimiento, User

TIPO_LABELS = {"ingreso": "Ingreso", "entrega": "Entrega", "ajuste": "Ajuste por conteo"}


def puede_cargar(user: User | None) -> bool:
    """Ingresos, conteos y configuración: administrador o responsable de laboratorio."""
    from app.user_roles import user_is_responsable_laboratorio

    return user is not None and (bool(user.is_admin) or user_is_responsable_laboratorio(user))


def puede_ver(user: User | None) -> bool:
    from app.auth_utils import user_can_access_stock_hub, user_can_gestionar_epp

    return puede_cargar(user) or user_can_gestionar_epp(user) or user_can_access_stock_hub(user)


def _talle(item: PersonalEppItem, raw: Any) -> str:
    return " ".join(str(raw or "").split()).upper()[:32] if item.stock_por_talle else ""


def _hoy() -> date:
    from app.utils.datetime_operacion import now_operacion_naive_local

    return now_operacion_naive_local().date()


def saldo(item_id: int, talle: str = "") -> int:
    return int(
        db.session.scalar(
            select(func.coalesce(func.sum(PersonalEppMovimiento.cantidad), 0)).where(
                PersonalEppMovimiento.item_id == int(item_id), PersonalEppMovimiento.talle == talle
            )
        )
        or 0
    )


def stock_de(item: PersonalEppItem | None, talle: Any = "") -> int | None:
    """Saldo para mostrar junto a un pedido (por talle si el ítem se cuenta por talle)."""
    if item is None:
        return None
    if item.stock_por_talle and not _talle(item, talle):
        return None
    return saldo(item.id, _talle(item, talle))


def saldos() -> dict[tuple[int, str], int]:
    rows = db.session.execute(
        select(PersonalEppMovimiento.item_id, PersonalEppMovimiento.talle, func.sum(PersonalEppMovimiento.cantidad))
        .group_by(PersonalEppMovimiento.item_id, PersonalEppMovimiento.talle)
    ).all()
    return {(int(i), t or ""): int(q or 0) for i, t, q in rows}


def resumen() -> list[dict[str, Any]]:
    """Por ítem activo: total, detalle por talle y alerta de mínimo."""
    s = saldos()
    items = db.session.scalars(
        select(PersonalEppItem).where(PersonalEppItem.activo.is_(True)).order_by(PersonalEppItem.categoria, PersonalEppItem.orden, PersonalEppItem.nombre)
    ).all()
    out = []
    for it in items:
        talles = sorted(((t, q) for (i, t), q in s.items() if i == it.id and (t or q)), key=lambda x: _orden_talle(x[0]))
        total = sum(q for _, q in talles) if it.stock_por_talle else s.get((it.id, ""), 0)
        out.append({
            "item": it,
            "total": total,
            "talles": [(t, q) for t, q in talles if t] if it.stock_por_talle else [],
            "sin_talle_cargado": s.get((it.id, ""), 0) if it.stock_por_talle else 0,
            "bajo_minimo": it.stock_minimo is not None and total <= int(it.stock_minimo),
            "negativo": any(q < 0 for _, q in talles) or total < 0,
        })
    return out


def _orden_talle(t: str) -> tuple[int, Any]:
    t = (t or "").strip().upper()
    letras = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"]
    if t.isdigit():
        return (0, int(t))
    if t in letras:
        return (1, letras.index(t))
    return (2, t)


def movimientos(limit: int = 100) -> list[PersonalEppMovimiento]:
    return list(
        db.session.scalars(
            select(PersonalEppMovimiento).order_by(PersonalEppMovimiento.created_at.desc(), PersonalEppMovimiento.id.desc()).limit(limit)
        ).unique()
    )


def _item_de(data: Any) -> tuple[PersonalEppItem | None, str | None]:
    raw = (data.get("item_id") or "").strip()
    item = db.session.get(PersonalEppItem, int(raw)) if raw.isdigit() else None
    if item is None or not item.activo:
        return None, "Elegí el elemento."
    return item, None


def _fecha(data: Any) -> date:
    try:
        return date.fromisoformat((data.get("fecha") or "").strip())
    except ValueError:
        return _hoy()


def registrar_ingreso(data: Any, user_id: int | None) -> str | None:
    item, err = _item_de(data)
    if err:
        return err
    talle = _talle(item, data.get("talle"))
    if item.stock_por_talle and not talle:
        return f"«{item.nombre}» se cuenta por talle: indicá el talle."
    raw = (data.get("cantidad") or "").strip()
    cantidad = int(raw) if raw.isdigit() else 0
    if not 1 <= cantidad <= 10000:
        return "La cantidad tiene que ser un número entre 1 y 10.000."
    db.session.add(PersonalEppMovimiento(
        item_id=item.id, talle=talle, tipo="ingreso", cantidad=cantidad, fecha=_fecha(data),
        proveedor=(data.get("proveedor") or "").strip()[:256], marca=(data.get("marca") or "").strip()[:128],
        observaciones=(data.get("observaciones") or "").strip()[:1000], user_id=user_id,
    ))
    return None


def registrar_conteo(data: Any, user_id: int | None) -> tuple[str | None, int]:
    """Conteo físico: registra la diferencia con el saldo del sistema. Devuelve (error, diferencia)."""
    item, err = _item_de(data)
    if err:
        return err, 0
    talle = _talle(item, data.get("talle"))
    if item.stock_por_talle and not talle:
        return f"«{item.nombre}» se cuenta por talle: indicá el talle contado.", 0
    raw = (data.get("contado") or "").strip()
    if not raw.isdigit():
        return "Indicá cuántas unidades contaste (0 o más).", 0
    diferencia = int(raw) - saldo(item.id, talle)
    if diferencia:
        db.session.add(PersonalEppMovimiento(
            item_id=item.id, talle=talle, tipo="ajuste", cantidad=diferencia, fecha=_fecha(data),
            observaciones=(data.get("observaciones") or "").strip()[:1000] or f"Conteo: {raw}", user_id=user_id,
        ))
    return None, diferencia


def descontar_entrega(entrega: PersonalEntregaEpp, user_id: int | None) -> str | None:
    """Descuenta del stock la entrega registrada. No hace commit. Devuelve un aviso si quedó sin stock."""
    item = entrega.item or db.session.get(PersonalEppItem, entrega.item_id)
    if item is None:
        return None
    talle = _talle(item, entrega.talle)
    cantidad = max(1, int(entrega.cantidad or 1))
    antes = saldo(item.id, talle)
    db.session.add(PersonalEppMovimiento(
        item_id=item.id, talle=talle, tipo="entrega", cantidad=-cantidad, fecha=entrega.fecha or _hoy(),
        entrega_id=entrega.id, user_id=user_id,
        observaciones=entrega.empleado.nombre_completo if entrega.empleado else "",
    ))
    # Solo avisa en elementos que ya empezaron a llevar stock (tienen ingreso o conteo): antes del
    # conteo inicial el saldo es 0 y el aviso sería ruido; el conteo corrige la diferencia.
    empezado = db.session.scalar(
        select(PersonalEppMovimiento.id).where(
            PersonalEppMovimiento.item_id == item.id, PersonalEppMovimiento.tipo.in_(("ingreso", "ajuste"))
        ).limit(1)
    )
    if empezado is not None and antes - cantidad < 0:
        detalle = f"{item.nombre}" + (f" talle {talle}" if talle else "")
        return (
            f"Atención: según el sistema no había stock suficiente de {detalle} (había {antes}). "
            "La entrega quedó registrada; revisá el stock de EPP o hacé un conteo."
        )
    return None


def guardar_config(data: Any) -> None:
    """Por ítem: si se cuenta por talle y el stock mínimo. El llamador hace commit."""
    for it in db.session.scalars(select(PersonalEppItem)).all():
        if f"min_{it.id}" not in data:
            continue
        it.stock_por_talle = (data.get(f"talle_{it.id}") or "") == "1"
        raw = (data.get(f"min_{it.id}") or "").strip()
        it.stock_minimo = int(raw) if raw.isdigit() else None


def fecha_local(dt: datetime | None) -> str:
    if dt is None:
        return ""
    from app.utils.datetime_operacion import operacion_zoneinfo

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(operacion_zoneinfo()).strftime("%d/%m/%Y %H:%M")
