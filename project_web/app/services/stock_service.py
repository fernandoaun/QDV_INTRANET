from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, List, Optional

from sqlalchemy import func, select, update

from app.extensions import db
from app.models import ConsumoStock, Equipo, IngresoStock, ProductoCatalogo, StockAjuste
from app.repositories.stock_repository import stock_repo
from app.utils.datetime_operacion import (
    format_consumo_stock_panel_datetime,
    now_operacion_local_iso_seconds,
    now_operacion_naive_local,
)
from app.utils.hipoclorito_producto import es_producto_entrega_operativo_hipoclorito
from app.utils.tipo_producto import normalize_tipo_producto


def producto_entrega_es_stock_hipoclorito(nombre_producto: str) -> bool:
    """True si el producto de la entrega es el hipoclorito operativo (cualquier alias; mismo criterio que Panel/SQL)."""
    return es_producto_entrega_operativo_hipoclorito(nombre_producto)


def _validate_cat(cat: str) -> str:
    c = (cat or "").strip().lower()
    if c not in ("materia_prima", "laboratorio", "producto_terminado"):
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


def ensure_producto(
    cat: str,
    nombre: str,
    tipo: str = "Normal",
    requiere_equipo: bool | None = None,
    is_stockable: bool | None = None,
    stock_minimo_alerta: Optional[float] = None,
    can_configure_alerta: bool = False,
) -> None:
    c = _validate_cat(cat)
    n = (nombre or "").strip()
    if not n:
        raise ValueError("Producto vacío.")
    t = normalize_tipo_producto(tipo)
    now = now_operacion_local_iso_seconds()
    row = db.session.execute(
        select(ProductoCatalogo).where(
            ProductoCatalogo.categoria == c,
            ProductoCatalogo.nombre_producto == n,
        )
    ).scalar_one_or_none()
    requiere_equipo_auto = t == "Filtro"
    requiere_equipo_cfg = bool(requiere_equipo) if requiere_equipo is not None else False
    requiere_equipo_final = bool(requiere_equipo_cfg or requiere_equipo_auto)
    is_stockable_final = bool(is_stockable) if is_stockable is not None else True
    if stock_minimo_alerta is None:
        min_alerta_final: Optional[float] = None
    else:
        min_alerta_final = float(stock_minimo_alerta)
        if min_alerta_final < 0:
            raise ValueError("El stock mínimo de alerta no puede ser negativo.")
    if row:
        row.activo = True
        row.tipo_producto = t
        row.requiere_equipo = requiere_equipo_final
        row.is_stockable = is_stockable_final
        if can_configure_alerta:
            row.stock_minimo_alerta = min_alerta_final if is_stockable_final else None
    else:
        db.session.add(
            ProductoCatalogo(
                categoria=c,
                nombre_producto=n,
                tipo_producto=t,
                requiere_equipo=requiere_equipo_final,
                is_stockable=is_stockable_final,
                stock_minimo_alerta=(min_alerta_final if (can_configure_alerta and is_stockable_final) else None),
                activo=True,
                created_at_iso=now,
            )
        )


def producto_requiere_equipo(cat: str, nombre: str) -> bool:
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
    # Compatibilidad: productos históricos tipo "Filtro" también exigen equipo.
    return bool(getattr(row, "requiere_equipo", False) or normalize_tipo_producto(row.tipo_producto) == "Filtro")


def producto_es_stockeable(cat: str, nombre: str) -> bool:
    c = _validate_cat(cat)
    key = (nombre or "").strip().lower()
    if not key:
        return True
    row = db.session.execute(
        select(ProductoCatalogo).where(
            ProductoCatalogo.categoria == c,
            func.lower(func.trim(ProductoCatalogo.nombre_producto)) == key,
            ProductoCatalogo.activo.is_(True),
        )
    ).scalar_one_or_none()
    if row is None:
        # Compatibilidad hacia atrás: lo no catalogado conserva la lógica histórica.
        return True
    return bool(getattr(row, "is_stockable", True))


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
    ajustes = db.session.scalar(
        select(func.coalesce(func.sum(StockAjuste.cantidad), 0.0)).where(
            StockAjuste.categoria == c,
            StockAjuste.producto == p,
            StockAjuste.marca == m,
        )
    )
    return max(float(ing or 0) - float(cons or 0) + float(ajustes or 0), 0.0)


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


def marcas_catalogo(cat: str, producto: str) -> list[str]:
    c = _validate_cat(cat)
    p = (producto or "").strip()
    rows = db.session.execute(
        select(IngresoStock.marca)
        .where(IngresoStock.categoria == c, IngresoStock.producto == p)
        .group_by(IngresoStock.marca)
        .order_by(IngresoStock.marca)
    ).all()
    return [str(marca) for (marca,) in rows if str(marca or "").strip()]


def _cantidad_consumida_en_ingreso(ingreso_id: int) -> float:
    v = db.session.scalar(
        select(func.coalesce(func.sum(ConsumoStock.cantidad), 0.0)).where(
            ConsumoStock.ingreso_stock_id == int(ingreso_id)
        )
    )
    return float(v or 0)


def _cantidad_ajustada_en_ingreso(ingreso_id: int) -> float:
    v = db.session.scalar(
        select(func.coalesce(func.sum(StockAjuste.cantidad), 0.0)).where(
            StockAjuste.ingreso_stock_id == int(ingreso_id)
        )
    )
    return float(v or 0)


def lotes_fifo_disponibles(categoria: str, producto: str, marca: str) -> list[dict[str, Any]]:
    """
    Líneas de ingreso con saldo disponible, orden FIFO (fecha → hora → id).
    El saldo por línea reparte el stock global producto+marca, de modo que consumos
    antiguos sin `ingreso_stock_id` sigan siendo coherentes con el total.
    """
    c = _validate_cat(categoria)
    p = (producto or "").strip()
    m = (marca or "").strip()
    if not p or not m:
        return []
    global_s = stock_actual(c, p, m)
    if global_s <= 0:
        return []
    ing_rows = list(
        db.session.scalars(
            select(IngresoStock)
            .where(
                IngresoStock.categoria == c,
                IngresoStock.producto == p,
                IngresoStock.marca == m,
            )
            .order_by(IngresoStock.fecha.asc(), IngresoStock.hora.asc(), IngresoStock.id.asc())
        ).all()
    )
    rem_global = float(global_s)
    out: list[dict[str, Any]] = []
    for ing in ing_rows:
        linked = _cantidad_consumida_en_ingreso(int(ing.id))
        adjusted = _cantidad_ajustada_en_ingreso(int(ing.id))
        raw_left = max(float(ing.cantidad or 0) - linked + adjusted, 0.0)
        take = min(raw_left, rem_global)
        if take > 0:
            uid = (getattr(ing, "unidad", None) or "").strip()
            out.append(
                {
                    "ingreso_id": int(ing.id),
                    "lote": (ing.lote or "").strip(),
                    "vencimiento": (ing.vencimiento or "").strip(),
                    "fecha_ingreso": ing.fecha,
                    "hora_ingreso": ing.hora,
                    "disponible": take,
                    "unidad": uid,
                    "es_fifo_primero": False,
                }
            )
        rem_global -= take
        if rem_global <= 1e-12:
            break
    if out:
        out[0]["es_fifo_primero"] = True
    return out


def lotes_ajustables(categoria: str, producto: str, marca: str) -> list[dict[str, Any]]:
    c = _validate_cat(categoria)
    p = (producto or "").strip()
    m = (marca or "").strip()
    if not p or not m:
        return []
    rows = list(
        db.session.scalars(
            select(IngresoStock)
            .where(
                IngresoStock.categoria == c,
                IngresoStock.producto == p,
                IngresoStock.marca == m,
            )
            .order_by(IngresoStock.fecha.asc(), IngresoStock.hora.asc(), IngresoStock.id.asc())
        ).all()
    )
    saldo_map = {int(row["ingreso_id"]): float(row["disponible"]) for row in lotes_fifo_disponibles(c, p, m)}
    out: list[dict[str, Any]] = []
    for ing in rows:
        uid = (getattr(ing, "unidad", None) or "").strip()
        out.append(
            {
                "ingreso_id": int(ing.id),
                "lote": (ing.lote or "").strip(),
                "vencimiento": (ing.vencimiento or "").strip(),
                "fecha_ingreso": ing.fecha,
                "hora_ingreso": ing.hora,
                "disponible": float(saldo_map.get(int(ing.id), 0.0)),
                "unidad": uid,
            }
        )
    return out


def saldo_consumible_lote(categoria: str, producto: str, marca: str, ingreso_id: int) -> float:
    for row in lotes_fifo_disponibles(categoria, producto, marca):
        if int(row["ingreso_id"]) == int(ingreso_id):
            return float(row["disponible"])
    return 0.0


def list_lotes_con_saldo_por_categoria(categoria: str) -> list[dict[str, Any]]:
    """Todas las líneas con saldo > 0 en una categoría (para existencias por lote)."""
    c = _validate_cat(categoria)
    pairs = db.session.execute(
        select(IngresoStock.producto, IngresoStock.marca).where(IngresoStock.categoria == c).distinct()
    ).all()
    rows_out: list[dict[str, Any]] = []
    for prod, marca in pairs:
        p, m = str(prod or "").strip(), str(marca or "").strip()
        if not p or not m:
            continue
        try:
            if not producto_es_stockeable(c, p):
                continue
        except Exception:
            continue
        for lot in lotes_fifo_disponibles(c, p, m):
            rows_out.append(
                {
                    "producto": p,
                    "marca": m,
                    "ingreso_id": lot["ingreso_id"],
                    "lote": lot["lote"],
                    "vencimiento": lot["vencimiento"],
                    "fecha_ingreso": lot["fecha_ingreso"],
                    "hora_ingreso": lot["hora_ingreso"],
                    "disponible": lot["disponible"],
                    "unidad": lot.get("unidad") or "",
                }
            )
    rows_out.sort(
        key=lambda x: (
            str(x["producto"]).lower(),
            str(x["marca"]).lower(),
            str(x["fecha_ingreso"]),
            int(x["ingreso_id"]),
        )
    )
    return rows_out


def equipos_activos() -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(Equipo).where(Equipo.activo.is_(True)).order_by(Equipo.nombre_equipo)
    ).all()
    return [{"id": r.id, "nombre_equipo": r.nombre_equipo} for r in rows]


def _ingreso_fecha_hora_y_created_iso(
    fecha: Optional[str], hora: Optional[str], fallback_now: datetime
) -> tuple[str, str, str]:
    f_str = (fecha or "").strip() or fallback_now.strftime("%Y-%m-%d")
    h_raw = (hora or "").strip() or fallback_now.strftime("%H:%M")
    parts = h_raw.replace(".", ":").split(":")
    if len(parts) < 2:
        raise ValueError("Hora de ingreso inválida.")
    try:
        hh = int(parts[0])
        mm = int(parts[1])
    except ValueError:
        raise ValueError("Hora de ingreso inválida.")
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("Hora de ingreso inválida.")
    h_str = f"{hh:02d}:{mm:02d}"
    try:
        reg_dt = datetime.strptime(f"{f_str} {h_str}", "%Y-%m-%d %H:%M")
    except ValueError as e:
        raise ValueError("Fecha u hora de ingreso inválida.") from e
    return f_str, h_str, reg_dt.isoformat(timespec="seconds")


def save_ingreso(
    categoria: str,
    producto: str,
    marca: str,
    vencimiento: str,
    lote: str,
    cantidad: float | None,
    operador: str,
    requiere_equipo: bool = False,
    is_stockable: bool = True,
    *,
    unidad: str = "",
    observaciones_ingreso: str = "",
    proveedor: str = "",
    cargado_por_user_id: int | None = None,
    fecha: Optional[str] = None,
    hora: Optional[str] = None,
    fecha_hora_fallback: Optional[datetime] = None,
) -> None:
    c = _validate_cat(categoria)
    p = (producto or "").strip()
    m = (marca or "").strip()
    v = (vencimiento or "").strip()
    l = (lote or "").strip()
    op = (operador or "").strip() or "sistema"
    stockable_effective = bool(is_stockable) if c == "materia_prima" else True
    if c == "materia_prima" and not stockable_effective:
        qty = 0.0
    else:
        try:
            qty = float(cantidad) if cantidad is not None else 0.0
        except (TypeError, ValueError):
            raise ValueError("La cantidad debe ser numérica.")
        if qty <= 0 or qty != qty:
            raise ValueError("La cantidad debe ser mayor a cero.")
    if not p or not m or not v or not l:
        raise ValueError("Completá producto, marca, vencimiento y lote.")
    ensure_producto(
        c,
        p,
        requiere_equipo=bool(requiere_equipo),
        is_stockable=stockable_effective,
        stock_minimo_alerta=None,
        can_configure_alerta=False,
    )
    fb = fecha_hora_fallback or now_operacion_naive_local()
    fecha_s, hora_s, created_iso = _ingreso_fecha_hora_y_created_iso(fecha, hora, fb)
    db.session.add(
        IngresoStock(
            categoria=c,
            producto=p,
            marca=m,
            vencimiento=v,
            lote=l,
            cantidad=qty,
            unidad=(unidad or "").strip()[:64] or "",
            fecha=fecha_s,
            hora=hora_s,
            operador=op,
            observaciones=(observaciones_ingreso or "").strip() or None,
            proveedor=(proveedor or "").strip()[:256] or None,
            cargado_por_user_id=cargado_por_user_id,
            created_at_iso=created_iso,
        )
    )
    db.session.commit()


def add_consumo_stock_record(
    categoria: str,
    producto: str,
    marca: str,
    cantidad: float,
    operador: str,
    observaciones: str = "",
    equipo_id: Optional[int] = None,
    *,
    fecha_hora: Optional[datetime] = None,
    skip_ledger_availability_check: bool = False,
    ingreso_stock_id: Optional[int] = None,
) -> ConsumoStock:
    """
    Registra un consumo en sesión (sin commit). Permite enlazar el mismo movimiento
    con otras entidades (p. ej. entregas) y hacer commit atómico en la capa superior.

    `skip_ledger_availability_check`: solo para flujos donde la capacidad ya se validó contra
    la fuente operativa de turno (p. ej. entrega hipoclorito «Cargar»). El registro sigue
    alimentando ingresos/consumos para trazabilidad; no desactiva marca ni equipo.
    """
    c = _validate_cat(categoria)
    p = (producto or "").strip()
    m = (marca or "").strip()
    op = (operador or "").strip() or "sistema"
    qty = float(cantidad)
    if not p:
        raise ValueError("Producto obligatorio.")
    if qty <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")
    is_stockable = producto_es_stockeable(c, p)
    ingreso_sql: Optional[int] = None
    if is_stockable:
        if not m:
            raise ValueError("Marca obligatoria para productos estoqueables.")
        if not skip_ledger_availability_check:
            if not ingreso_stock_id:
                raise ValueError("Seleccioná el lote (línea de ingreso) del cual se descuenta el stock.")
            iid = int(ingreso_stock_id)
            ing_row = db.session.get(IngresoStock, iid)
            if ing_row is None:
                raise ValueError("Lote / ingreso no válido.")
            if (
                (ing_row.categoria or "").strip() != c
                or (ing_row.producto or "").strip() != p
                or (ing_row.marca or "").strip() != m
            ):
                raise ValueError("El lote seleccionado no corresponde a este producto y marca.")
            cap = saldo_consumible_lote(c, p, m, iid)
            if qty > cap + 1e-9:
                raise ValueError(
                    "La cantidad supera lo disponible en ese lote (orden FIFO). "
                    "Reducí el monto o registrá otro consumo desde otro lote."
                )
            st = stock_actual(c, p, m)
            if st <= 0:
                raise ValueError("No hay stock disponible.")
            if qty > st + 1e-9:
                raise ValueError("No podés consumir más de lo disponible.")
            ingreso_sql = iid
    elif not m:
        # Trazabilidad mínima cuando no se usa stock por marca.
        m = "N/A"

    eq_sql: Optional[int] = None
    if producto_requiere_equipo(c, p):
        if equipo_id is None:
            raise ValueError("Este producto requiere indicar equipo.")
        eid = int(equipo_id)
        row = db.session.get(Equipo, eid)
        if row is None or not row.activo:
            raise ValueError("Equipo inválido o inactivo.")
        eq_sql = eid
    now = fecha_hora or now_operacion_naive_local()
    rec = ConsumoStock(
        categoria=c,
        producto=p,
        marca=m,
        cantidad=qty,
        fecha=now.strftime("%Y-%m-%d"),
        hora=now.strftime("%H:%M"),
        operador=op,
        observaciones=(observaciones or "").strip(),
        equipo_id=eq_sql,
        ingreso_stock_id=ingreso_sql,
        created_at_iso=now.isoformat(timespec="seconds"),
    )
    db.session.add(rec)
    return rec


def save_consumo(
    categoria: str,
    producto: str,
    marca: str,
    cantidad: float,
    operador: str,
    observaciones: str = "",
    equipo_id: Optional[int] = None,
    ingreso_stock_id: Optional[int] = None,
) -> None:
    add_consumo_stock_record(
        categoria,
        producto,
        marca,
        cantidad,
        operador,
        observaciones,
        equipo_id,
        ingreso_stock_id=ingreso_stock_id,
    )
    db.session.commit()


def stock_consolidado(cat: str) -> list[dict[str, Any]]:
    c = _validate_cat(cat)
    ing = stock_repo.sum_ingresos_by_producto(c)
    con = stock_repo.sum_consumos_by_producto(c)
    ajustes = stock_repo.sum_ajustes_by_producto(c)
    catalog_map = stock_repo.catalog_is_stockable_map(c)
    try:
        catalog_names = set(productos_catalogo(c))
    except Exception:
        catalog_names = set()
    keys = catalog_names | set(ing) | set(con) | set(ajustes) | set(catalog_map)
    out: list[dict[str, Any]] = []
    for prod in sorted(keys, key=lambda x: str(x).lower()):
        is_stockable = bool(catalog_map.get(str(prod), True))
        s = float(ing.get(prod, 0) or 0) - float(con.get(prod, 0) or 0) + float(ajustes.get(prod, 0) or 0)
        s = max(s, 0.0)
        if is_stockable:
            out.append({"producto": str(prod), "stock": s, "is_stockable": True})
        else:
            out.append({"producto": str(prod), "stock": 0.0, "is_stockable": False})
    return out


def stock_consolidado_todas() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cat in ("materia_prima", "laboratorio", "producto_terminado"):
        for it in stock_consolidado(cat):
            out.append(
                {
                    "categoria": cat,
                    "producto": str(it["producto"]),
                    "stock": float(it["stock"] or 0),
                    "is_stockable": bool(it.get("is_stockable", True)),
                }
            )
    out.sort(key=lambda x: (str(x["categoria"]), str(x["producto"]).lower()))
    return out


def stock_total_producto(cat: str, producto: str) -> float:
    c = _validate_cat(cat)
    p = (producto or "").strip()
    if not p:
        return 0.0
    ing = db.session.scalar(
        select(func.coalesce(func.sum(IngresoStock.cantidad), 0.0)).where(
            IngresoStock.categoria == c,
            IngresoStock.producto == p,
        )
    )
    cons = db.session.scalar(
        select(func.coalesce(func.sum(ConsumoStock.cantidad), 0.0)).where(
            ConsumoStock.categoria == c,
            ConsumoStock.producto == p,
        )
    )
    ajustes = db.session.scalar(
        select(func.coalesce(func.sum(StockAjuste.cantidad), 0.0)).where(
            StockAjuste.categoria == c,
            StockAjuste.producto == p,
        )
    )
    return max(float(ing or 0) - float(cons or 0) + float(ajustes or 0), 0.0)


def _nivel_alerta_panel(stock_actual: float, stock_minimo: float) -> str | None:
    """
    Decide si un producto entra en el panel de alertas y con qué severidad.

    Usa redondeo a 2 decimales (misma precisión que la UI) para alinear criterio
    operativo con lo que ve el usuario.

    Returns:
        None — no mostrar (stock efectivo > mínimo).
        "limite" — stock en el mínimo (alerta preventiva).
        "critico" — stock por debajo del mínimo.
    """
    a = round(float(stock_actual), 2)
    m = round(float(stock_minimo), 2)
    if a > m:
        return None
    if a == m:
        return "limite"
    return "critico"


def alertas_bajo_stock(limit: int = 100) -> list[dict[str, Any]]:
    n = int(limit or 100)
    if n < 1:
        n = 1
    if n > 1000:
        n = 1000
    rows = stock_repo.list_catalog_con_umbral_alerta()
    out: list[dict[str, Any]] = []
    for r in rows:
        minimo = float(r.stock_minimo_alerta or 0)
        actual = stock_total_producto(str(r.categoria), str(r.nombre_producto))
        nivel = _nivel_alerta_panel(actual, minimo)
        if nivel is None:
            continue
        out.append(
            {
                "categoria": r.categoria,
                "producto": r.nombre_producto,
                "stock_actual": actual,
                "stock_minimo_alerta": minimo,
                "faltante": max(minimo - actual, 0.0),
                "nivel_alerta": nivel,
                "mensaje_alerta": (
                    "Stock en mínimo" if nivel == "limite" else "Stock por debajo del mínimo"
                ),
            }
        )
    # Criticidad: primero stock más bajo, luego mayor faltante relativo
    out.sort(key=lambda x: (float(x["stock_actual"]), -float(x["faltante"]), str(x["producto"]).lower()))
    return out[:n]


def _consumo_rows_to_dicts(
    rows: list[ConsumoStock],
    *,
    include_id: bool,
    include_categoria_producto: bool,
) -> list[dict[str, Any]]:
    eq_ids = {int(r.equipo_id) for r in rows if r.equipo_id is not None}
    eq_map = stock_repo.equipo_nombres_by_ids(eq_ids)
    ing_ids = {int(r.ingreso_stock_id) for r in rows if getattr(r, "ingreso_stock_id", None)}
    ing_lote: dict[int, str] = {}
    if ing_ids:
        for ing in db.session.scalars(select(IngresoStock).where(IngresoStock.id.in_(ing_ids))).all():
            ing_lote[int(ing.id)] = (ing.lote or "").strip()
    out: list[dict[str, Any]] = []
    for r in rows:
        eq_name = ""
        if r.equipo_id is not None:
            eq_name = (eq_map.get(int(r.equipo_id)) or "").strip()
        iid = getattr(r, "ingreso_stock_id", None)
        lote_txt = ing_lote.get(int(iid), "") if iid is not None else ""
        item: dict[str, Any] = {
            "fecha": r.fecha,
            "hora": r.hora,
            "fecha_hora": format_consumo_stock_panel_datetime(r.created_at_iso, r.fecha, r.hora),
            "marca": r.marca,
            "cantidad": r.cantidad,
            "operador": r.operador,
            "equipo": eq_name,
            "observaciones": r.observaciones or "",
            "lote": lote_txt,
            "ingreso_stock_id": int(iid) if iid is not None else None,
        }
        if include_id:
            item["id"] = r.id
        if include_categoria_producto:
            item["categoria"] = r.categoria
            item["producto"] = r.producto
        out.append(item)
    return out


def consumos_recientes(cat: str, producto: str, limit: int = 50) -> list[dict[str, Any]]:
    c = _validate_cat(cat)
    p = (producto or "").strip()
    if not p:
        return []
    n = int(limit or 50)
    if n < 1:
        n = 1
    if n > 200:
        n = 200
    rows = stock_repo.list_consumos_for_product(c, p, n)
    return _consumo_rows_to_dicts(rows, include_id=True, include_categoria_producto=False)


def consumos_ultimos_dias(dias: int = 30, limit: int = 300) -> list[dict[str, Any]]:
    d = int(dias or 30)
    if d < 1:
        d = 1
    if d > 365:
        d = 365
    n = int(limit or 300)
    if n < 1:
        n = 1
    if n > 2000:
        n = 2000
    cutoff_iso = (now_operacion_naive_local() - timedelta(days=d)).strftime("%Y-%m-%d")
    rows = stock_repo.list_consumos_since_fecha(cutoff_iso, n)
    return _consumo_rows_to_dicts(rows, include_id=False, include_categoria_producto=True)


def build_stock_hub_template_context(user: Any) -> dict[str, Any]:
    from app.auth_utils import user_can_view_stock_historial

    consumos_30d: list[dict[str, Any]] = []
    if user is not None and user_can_view_stock_historial(user):
        try:
            consumos_30d = consumos_ultimos_dias(30, limit=300)
        except Exception:
            consumos_30d = []
    return {"consumos_30d": consumos_30d, "user_is_admin": bool(getattr(user, "is_admin", False))}


def load_stock_consumo_view_data(cat: str, producto: str, marca_sel: str = "") -> dict[str, Any]:
    es_stockeable = True
    if producto:
        try:
            es_stockeable = producto_es_stockeable(cat, producto)
        except Exception:
            es_stockeable = True
    marcas: list[str] = []
    if producto:
        try:
            if es_stockeable:
                marcas = marcas_con_stock(cat, producto)
            else:
                marcas = marcas_catalogo(cat, producto)
        except Exception:
            marcas = []
    marca_eff = (marca_sel or "").strip()
    if es_stockeable and producto and marcas and not marca_eff and len(marcas) == 1:
        marca_eff = marcas[0]
    lotes: list[dict[str, Any]] = []
    if producto and marca_eff and es_stockeable:
        try:
            lotes = lotes_fifo_disponibles(cat, producto, marca_eff)
        except Exception:
            lotes = []
    productos: list[str] = []
    try:
        productos = productos_catalogo(cat)
    except Exception:
        productos = []
    recientes: list[dict[str, Any]] = []
    if producto:
        try:
            recientes = consumos_recientes(cat, producto, limit=30)
        except Exception:
            recientes = []
    return {
        "producto_es_stockeable": es_stockeable,
        "marcas": marcas,
        "marca_sel": marca_eff,
        "lotes": lotes,
        "productos": productos,
        "consumos_recientes": recientes,
        "equipos": equipos_activos(),
        "producto_requiere_equipo": producto_requiere_equipo(cat, producto) if producto else False,
    }


def save_consumo_from_web_form(form: Any, *, default_operador: str) -> None:
    expected_op = (default_operador or "").strip().lower()
    submitted_op = (form.get("operador") or "").strip().lower()
    if not expected_op or submitted_op != expected_op:
        raise ValueError(
            "El operador del consumo debe coincidir con tu usuario de sesión (y turno activo si aplica)."
        )
    eq = form.get("equipo_id")
    raw_ing = (form.get("ingreso_stock_id") or "").strip()
    ing_id: Optional[int] = int(raw_ing) if raw_ing.isdigit() else None
    save_consumo(
        form.get("categoria") or "",
        form.get("producto") or "",
        form.get("marca") or "",
        float((form.get("cantidad") or "0").replace(",", ".")),
        default_operador,
        form.get("observaciones") or "",
        int(eq) if eq else None,
        ingreso_stock_id=ing_id,
    )


def _ajuste_rows_to_dicts(rows: list[StockAjuste]) -> list[dict[str, Any]]:
    ing_ids = {int(r.ingreso_stock_id) for r in rows if getattr(r, "ingreso_stock_id", None)}
    ing_lote: dict[int, str] = {}
    if ing_ids:
        for ing in db.session.scalars(select(IngresoStock).where(IngresoStock.id.in_(ing_ids))).all():
            ing_lote[int(ing.id)] = (ing.lote or "").strip()
    out: list[dict[str, Any]] = []
    for r in rows:
        iid = getattr(r, "ingreso_stock_id", None)
        out.append(
            {
                "id": r.id,
                "fecha": r.fecha,
                "hora": r.hora,
                "categoria": r.categoria,
                "producto": r.producto,
                "marca": r.marca,
                "lote": ing_lote.get(int(iid), "") if iid is not None else "",
                "cantidad": r.cantidad,
                "tipo": "Positivo" if float(r.cantidad or 0) >= 0 else "Negativo",
                "motivo": r.motivo,
                "operador": r.operador,
                "observaciones": r.observaciones or "",
                "ingreso_stock_id": int(iid) if iid is not None else None,
                "admin_user_id": r.admin_user_id,
                "created_at_iso": r.created_at_iso,
            }
        )
    return out


def ajustes_recientes(limit: int = 100) -> list[dict[str, Any]]:
    return _ajuste_rows_to_dicts(stock_repo.list_ajustes_recent(limit))


def load_stock_ajuste_view_data(cat: str, producto: str, marca_sel: str = "") -> dict[str, Any]:
    c = _validate_cat(cat)
    productos = productos_catalogo(c)
    producto_sel = (producto or "").strip()
    es_stockeable = producto_es_stockeable(c, producto_sel) if producto_sel else True
    marcas: list[str] = []
    if producto_sel and es_stockeable:
        marcas = marcas_catalogo(c, producto_sel)
    marca_eff = (marca_sel or "").strip()
    if producto_sel and marcas and not marca_eff and len(marcas) == 1:
        marca_eff = marcas[0]
    lotes: list[dict[str, Any]] = []
    if producto_sel and marca_eff and es_stockeable:
        lotes = lotes_ajustables(c, producto_sel, marca_eff)
    return {
        "productos": productos,
        "producto_sel": producto_sel,
        "producto_es_stockeable": es_stockeable,
        "marcas": marcas,
        "marca_sel": marca_eff,
        "lotes": lotes,
        "ajustes_recientes": ajustes_recientes(100),
    }


def save_ajuste_from_web_form(form: Any, *, operador: str, admin_user_id: int | None) -> StockAjuste:
    c = _validate_cat(form.get("categoria") or "")
    p = (form.get("producto") or "").strip()
    m = (form.get("marca") or "").strip()
    motivo = (form.get("motivo") or "").strip()
    tipo = (form.get("tipo") or "").strip()
    raw_ing = (form.get("ingreso_stock_id") or "").strip()
    if not p:
        raise ValueError("Producto obligatorio.")
    if not producto_es_stockeable(c, p):
        raise ValueError("Solo se pueden ajustar productos estoqueables.")
    if not m:
        raise ValueError("Marca obligatoria.")
    if not raw_ing.isdigit():
        raise ValueError("Seleccioná el lote de ingreso a ajustar.")
    if tipo not in ("positivo", "negativo"):
        raise ValueError("Tipo de ajuste inválido.")
    if not motivo:
        raise ValueError("Motivo obligatorio.")
    try:
        qty_abs = float((form.get("cantidad") or "0").replace(",", "."))
    except ValueError as exc:
        raise ValueError("La cantidad debe ser numérica.") from exc
    if qty_abs <= 0 or math.isnan(qty_abs):
        raise ValueError("La cantidad debe ser mayor a cero.")

    iid = int(raw_ing)
    ing = db.session.get(IngresoStock, iid)
    if ing is None:
        raise ValueError("Lote / ingreso no válido.")
    if (
        (ing.categoria or "").strip() != c
        or (ing.producto or "").strip() != p
        or (ing.marca or "").strip() != m
    ):
        raise ValueError("El lote seleccionado no corresponde a este producto y marca.")

    signed_qty = qty_abs if tipo == "positivo" else -qty_abs
    if signed_qty < 0:
        disponible = saldo_consumible_lote(c, p, m, iid)
        if qty_abs > disponible + 1e-9:
            raise ValueError("El ajuste negativo no puede dejar el lote con saldo negativo.")

    now = now_operacion_naive_local()
    rec = StockAjuste(
        categoria=c,
        producto=p,
        marca=m,
        cantidad=signed_qty,
        fecha=now.strftime("%Y-%m-%d"),
        hora=now.strftime("%H:%M"),
        operador=(operador or "").strip() or "admin",
        motivo=motivo,
        observaciones=(form.get("observaciones") or "").strip() or None,
        ingreso_stock_id=iid,
        admin_user_id=admin_user_id,
        created_at_iso=now.isoformat(timespec="seconds"),
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def save_ingreso_from_web_form(
    form: Any,
    *,
    categoria_post: str,
    username_fallback: str | None,
    default_operador: str,
    fecha_hora_fallback: datetime,
    cargado_por_user_id: int | None = None,
) -> None:
    is_stockable = (form.get("is_stockable") or "1").strip() != "0"
    if categoria_post != "materia_prima":
        is_stockable = True
    operador_final = (form.get("operador") or "").strip() or default_operador
    if not operador_final and username_fallback and (username_fallback or "").strip():
        operador_final = (username_fallback or "").strip()
    if categoria_post == "materia_prima" and not is_stockable:
        cantidad_arg: float | None = 0.0
    else:
        qraw = (form.get("cantidad") or "").strip()
        cantidad_arg = float(qraw.replace(",", ".")) if qraw else 0.0
    save_ingreso(
        form.get("categoria") or "",
        form.get("producto") or "",
        form.get("marca") or "",
        form.get("vencimiento") or "",
        form.get("lote") or "",
        cantidad_arg,
        operador_final,
        (form.get("requiere_equipo") == "1"),
        is_stockable,
        unidad=(form.get("unidad") or "").strip(),
        observaciones_ingreso=(form.get("observaciones_ingreso") or "").strip(),
        proveedor=(form.get("proveedor") or "").strip(),
        cargado_por_user_id=cargado_por_user_id,
        fecha=(form.get("fecha_ingreso") or "").strip() or None,
        hora=(form.get("hora_ingreso") or "").strip() or None,
        fecha_hora_fallback=fecha_hora_fallback,
    )


def build_stock_ver_template_context(categoria_arg: str) -> dict[str, Any]:
    cat = (categoria_arg or "todas").strip()
    try:
        if cat == "todas":
            items = stock_consolidado_todas()
        else:
            items = stock_consolidado(cat)
    except Exception:
        items = []
    lotes_items: list[dict[str, Any]] = []
    try:
        if cat != "todas":
            lotes_items = list_lotes_con_saldo_por_categoria(cat)
    except Exception:
        lotes_items = []
    return {"categoria": cat, "items": items, "lotes_items": lotes_items}


def list_productos_catalogo_rows(categoria: str | None = None) -> list[ProductoCatalogo]:
    q = select(ProductoCatalogo).where(ProductoCatalogo.activo.is_(True))
    if categoria:
        q = q.where(ProductoCatalogo.categoria == _validate_cat(categoria))
    return list(db.session.scalars(q.order_by(ProductoCatalogo.categoria, ProductoCatalogo.nombre_producto)).all())


def get_catalog_product(producto_id: int) -> ProductoCatalogo | None:
    row = db.session.get(ProductoCatalogo, int(producto_id))
    if row is None or not bool(getattr(row, "activo", True)):
        return None
    return row


def create_catalog_product(
    categoria: str,
    nombre_producto: str,
    *,
    stock_minimo_alerta: float,
    tipo_producto: str = "Normal",
    requiere_equipo: bool = False,
    is_stockable: bool = True,
) -> None:
    c = _validate_cat(categoria)
    n = (nombre_producto or "").strip()
    if not n:
        raise ValueError("El nombre del producto es obligatorio.")
    try:
        smin = float(stock_minimo_alerta)
    except (TypeError, ValueError):
        raise ValueError("Stock mínimo de alerta inválido.")
    if smin < 0 or not math.isfinite(smin):
        raise ValueError("El stock mínimo de alerta no puede ser negativo.")
    key = n.lower()
    dup = db.session.execute(
        select(ProductoCatalogo).where(
            ProductoCatalogo.categoria == c,
            func.lower(func.trim(ProductoCatalogo.nombre_producto)) == key,
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ValueError("Ya existe un producto con ese nombre en la categoría.")
    stockable_f = bool(is_stockable) if c == "materia_prima" else True
    ensure_producto(
        c,
        n,
        tipo=tipo_producto,
        requiere_equipo=bool(requiere_equipo),
        is_stockable=stockable_f,
        stock_minimo_alerta=smin if stockable_f else None,
        can_configure_alerta=True,
    )
    db.session.commit()


def reassign_catalog_product_categoria(producto_id: int, nueva_categoria: str) -> None:
    """
    Cambia la categoría de un ítem del catálogo y alinea ingresos/consumos de stock
    con el mismo nombre de producto (misma cadena guardada en BD).
    """
    row = db.session.get(ProductoCatalogo, int(producto_id))
    if row is None or not bool(getattr(row, "activo", True)):
        raise ValueError("Producto no encontrado.")
    old_c = str(row.categoria or "").strip()
    new_c = _validate_cat(nueva_categoria)
    if old_c == new_c:
        return
    n = (row.nombre_producto or "").strip()
    if not n:
        raise ValueError("Nombre de producto inválido.")
    key = n.lower()
    dup = db.session.execute(
        select(ProductoCatalogo).where(
            ProductoCatalogo.categoria == new_c,
            func.lower(func.trim(ProductoCatalogo.nombre_producto)) == key,
            ProductoCatalogo.id != int(row.id),
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ValueError(
            "Ya existe un producto con el mismo nombre en la categoría destino. "
            "No se puede mover hasta resolver el duplicado."
        )
    db.session.execute(
        update(IngresoStock)
        .where(IngresoStock.categoria == old_c, IngresoStock.producto == n)
        .values(categoria=new_c)
    )
    db.session.execute(
        update(ConsumoStock)
        .where(ConsumoStock.categoria == old_c, ConsumoStock.producto == n)
        .values(categoria=new_c)
    )
    db.session.execute(
        update(StockAjuste)
        .where(StockAjuste.categoria == old_c, StockAjuste.producto == n)
        .values(categoria=new_c)
    )
    row.categoria = new_c
    if new_c != "materia_prima":
        row.is_stockable = True
    db.session.flush()


def update_catalog_product_admin(
    producto_id: int,
    *,
    stock_minimo_alerta: Optional[float] = None,
    requiere_equipo: bool = False,
    is_stockable: Optional[bool] = None,
    tipo_producto: Optional[str] = None,
) -> None:
    row = db.session.get(ProductoCatalogo, int(producto_id))
    if row is None:
        raise ValueError("Producto no encontrado.")
    if stock_minimo_alerta is not None:
        v = float(stock_minimo_alerta)
        if v < 0 or not math.isfinite(v):
            raise ValueError("Stock mínimo de alerta inválido.")
        row.stock_minimo_alerta = v if bool(getattr(row, "is_stockable", True)) else None
    row.requiere_equipo = bool(requiere_equipo)
    if normalize_tipo_producto(row.tipo_producto) == "Filtro":
        row.requiere_equipo = True
    if is_stockable is not None and str(row.categoria) == "materia_prima":
        row.is_stockable = bool(is_stockable)
        if not row.is_stockable:
            row.stock_minimo_alerta = None
    if tipo_producto is not None and (tipo_producto or "").strip():
        row.tipo_producto = normalize_tipo_producto(tipo_producto)
        if normalize_tipo_producto(row.tipo_producto) == "Filtro":
            row.requiere_equipo = True
    db.session.commit()
