from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, List, Optional

from sqlalchemy import func, select

from app.extensions import db
from app.models import ConsumoStock, Equipo, IngresoStock, ProductoCatalogo
from app.repositories.stock_repository import stock_repo
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
    now = datetime.now().isoformat(timespec="seconds")
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
    stock_minimo_alerta: Optional[float] = None,
    actor_is_admin: bool = False,
    *,
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
    if stock_minimo_alerta is not None and not bool(actor_is_admin):
        raise ValueError("Solo administradores pueden configurar stock mínimo de alerta.")
    ensure_producto(
        c,
        p,
        requiere_equipo=bool(requiere_equipo),
        is_stockable=stockable_effective,
        stock_minimo_alerta=stock_minimo_alerta,
        can_configure_alerta=bool(actor_is_admin),
    )
    fb = fecha_hora_fallback or datetime.now()
    fecha_s, hora_s, created_iso = _ingreso_fecha_hora_y_created_iso(fecha, hora, fb)
    db.session.add(
        IngresoStock(
            categoria=c,
            producto=p,
            marca=m,
            vencimiento=v,
            lote=l,
            cantidad=qty,
            fecha=fecha_s,
            hora=hora_s,
            operador=op,
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
    if is_stockable:
        if not m:
            raise ValueError("Marca obligatoria para productos estoqueables.")
        if not skip_ledger_availability_check:
            st = stock_actual(c, p, m)
            if st <= 0:
                raise ValueError("No hay stock disponible.")
            if qty > st:
                raise ValueError("No podés consumir más de lo disponible.")
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
    now = fecha_hora or datetime.now()
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
) -> None:
    add_consumo_stock_record(
        categoria,
        producto,
        marca,
        cantidad,
        operador,
        observaciones,
        equipo_id,
    )
    db.session.commit()


def stock_consolidado(cat: str) -> list[dict[str, Any]]:
    c = _validate_cat(cat)
    ing = stock_repo.sum_ingresos_by_producto(c)
    con = stock_repo.sum_consumos_by_producto(c)
    catalog_map = stock_repo.catalog_is_stockable_map(c)
    keys = set(ing) | set(con) | set(catalog_map)
    out: list[dict[str, Any]] = []
    for prod in sorted(keys, key=lambda x: str(x).lower()):
        is_stockable = bool(catalog_map.get(str(prod), True))
        s = float(ing.get(prod, 0) or 0) - float(con.get(prod, 0) or 0)
        if is_stockable and s > 0:
            out.append({"producto": str(prod), "stock": s})
        elif not is_stockable:
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
    return max(float(ing or 0) - float(cons or 0), 0.0)


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
        if actual <= minimo:
            out.append(
                {
                    "categoria": r.categoria,
                    "producto": r.nombre_producto,
                    "stock_actual": actual,
                    "stock_minimo_alerta": minimo,
                    "faltante": max(minimo - actual, 0.0),
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
    out: list[dict[str, Any]] = []
    for r in rows:
        eq_name = ""
        if r.equipo_id is not None:
            eq_name = (eq_map.get(int(r.equipo_id)) or "").strip()
        item: dict[str, Any] = {
            "fecha": r.fecha,
            "hora": r.hora,
            "marca": r.marca,
            "cantidad": r.cantidad,
            "operador": r.operador,
            "equipo": eq_name,
            "observaciones": r.observaciones or "",
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
    cutoff_iso = (datetime.now() - timedelta(days=d)).strftime("%Y-%m-%d")
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
    return {"consumos_30d": consumos_30d}


def load_stock_consumo_view_data(cat: str, producto: str) -> dict[str, Any]:
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
    save_consumo(
        form.get("categoria") or "",
        form.get("producto") or "",
        form.get("marca") or "",
        float((form.get("cantidad") or "0").replace(",", ".")),
        default_operador,
        form.get("observaciones") or "",
        int(eq) if eq else None,
    )


def save_ingreso_from_web_form(
    form: Any,
    *,
    categoria_post: str,
    username_fallback: str | None,
    default_operador: str,
    actor_is_admin: bool,
    fecha_hora_fallback: datetime,
) -> None:
    smin_raw = (form.get("stock_minimo_alerta") or "").strip()
    smin_val = float(smin_raw.replace(",", ".")) if smin_raw else None
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
        smin_val,
        bool(actor_is_admin),
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
    return {"categoria": cat, "items": items}
