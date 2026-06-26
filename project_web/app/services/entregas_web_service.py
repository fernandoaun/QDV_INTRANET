"""
Lógica de negocio compartida por las vistas HTML de Entregas (sin acoplar a request/response).

Las rutas solo resuelven permisos, HTTP y redirecciones; acá vive validación de formularios,
catálogos de UI y operaciones de catálogo admin.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.constants import (
    ENTREGA_CLIENTE_PENDIENTE_LOGISTICA,
    ENTREGA_LUGAR_PENDIENTE_LOGISTICA,
    ENTREGAS_MARCA_PRODUCTO_TERMINADO_TRAZA,
    ENTREGAS_STOCK_CATEGORIA,
    HIPOCLORITO_STOCK_NOMBRE_PRODUCTO,
)
from app.extensions import db
from app.models import (
    ChoferEntrega,
    ClienteEntrega,
    Entrega,
    EntregaEvento,
    LugarEntrega,
    ProductoTerminado,
    User,
)
from app.services import entregas_catalog_service, entregas_service, operational_informed_stock, stock_service
from app.utils.datetime_operacion import now_operacion_local_iso_seconds
from app.utils.hipoclorito_producto import (
    aliases_entrega_lower_sorted,
    clave_catalogo_stock_producto_terminado,
)

UNIDAD_ENTREGA = "L"
_HORA_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")


def parse_entrega_float(raw: str | None) -> float:
    return float((raw or "").replace(",", ".").strip() or 0)


def parse_entrega_positive_int(raw: str | None) -> int | None:
    s = (raw or "").strip()
    if not s.isdigit():
        return None
    v = int(s)
    return v if v > 0 else None


def normalize_hora_prevista(raw: str | None) -> str:
    h = (raw or "").strip()
    if not h:
        return ""
    if not _HORA_HHMM_RE.fullmatch(h):
        raise ValueError("La hora debe tener formato HH:MM.")
    hh, mm = h.split(":", 1)
    if int(hh) > 23 or int(mm) > 59:
        raise ValueError("La hora prevista es inválida.")
    return h


def stock_fields_entrega(producto_stock_name: str, stock_equipo_id_raw: str) -> tuple[str | None, str | None, int | None]:
    if not stock_service.producto_entrega_es_stock_hipoclorito(producto_stock_name):
        return None, None, None
    marca = (ENTREGAS_MARCA_PRODUCTO_TERMINADO_TRAZA or "").strip()
    eq_raw = (stock_equipo_id_raw or "").strip()
    eq_id: int | None = int(eq_raw) if eq_raw.isdigit() else None
    return ENTREGAS_STOCK_CATEGORIA, marca, eq_id


def validar_entrega_completa(
    cliente_id: int | None,
    lugar_id: int | None,
    producto_tid: int | None,
    chofer_id: int | None,
) -> tuple[str | None, object | None, object | None, object | None, ChoferEntrega | None]:
    if not cliente_id or not lugar_id or not producto_tid or not chofer_id:
        return ("Cliente, lugar de entrega, producto terminado y chofer son obligatorios.", None, None, None, None)
    cli = entregas_catalog_service.get_cliente_activo(cliente_id)
    if cli is None:
        return ("Cliente inválido o inactivo.", None, None, None, None)
    lug = entregas_catalog_service.get_lugar_entrega_validado(lugar_id, cliente_id)
    if lug is None:
        return ("El lugar de entrega no corresponde al cliente o está inactivo.", None, None, None, None)
    pt = entregas_catalog_service.get_producto_terminado_activo(producto_tid)
    if pt is None:
        return ("Producto terminado inválido o inactivo.", None, None, None, None)
    ch: ChoferEntrega | None = None
    if chofer_id:
        ch = entregas_catalog_service.get_chofer_activo(chofer_id)
        if ch is None:
            return ("Chofer inválido o inactivo.", None, None, None, None)
    return (None, cli, lug, pt, ch)


def validar_solo_logistica(
    cliente_id: int | None,
    lugar_id: int | None,
    chofer_id: int | None,
) -> tuple[str | None, object | None, object | None, ChoferEntrega | None]:
    if not cliente_id or not lugar_id:
        return ("Cliente y lugar de entrega son obligatorios.", None, None, None)
    cli = entregas_catalog_service.get_cliente_activo(cliente_id)
    if cli is None:
        return ("Cliente inválido o inactivo.", None, None, None)
    lug = entregas_catalog_service.get_lugar_entrega_validado(lugar_id, cliente_id)
    if lug is None:
        return ("El lugar de entrega no corresponde al cliente o está inactivo.", None, None, None)
    ch: ChoferEntrega | None = None
    if chofer_id:
        ch = entregas_catalog_service.get_chofer_activo(chofer_id)
        if ch is None:
            return ("Chofer inválido o inactivo.", None, None, None)
    return (None, cli, lug, ch)


def assign_catalogo_a_entrega(
    ent: Entrega,
    cli: object,
    lug: object,
    pt: object,
    ch: ChoferEntrega | None,
) -> None:
    ent.cliente_id = int(cli.id)
    ent.lugar_entrega_id = int(lug.id)
    ent.producto_terminado_id = int(pt.id)
    ent.cliente = str(cli.nombre).strip()
    ent.lugar_entrega = str(lug.nombre).strip()
    ent.producto = str(pt.stock_producto or "").strip()
    ent.unidad = UNIDAD_ENTREGA
    ent.chofer_entrega_id = int(ch.id) if ch else None
    ent.chofer_previsto = str(ch.nombre).strip() if ch else None


def assign_logistica_entrega(ent: Entrega, cli: object, lug: object, ch: ChoferEntrega | None) -> None:
    ent.cliente_id = int(cli.id)
    ent.lugar_entrega_id = int(lug.id)
    ent.cliente = str(cli.nombre).strip()
    ent.lugar_entrega = str(lug.nombre).strip()
    ent.chofer_entrega_id = int(ch.id) if ch else None
    ent.chofer_previsto = str(ch.nombre).strip() if ch else None


def form_catalog_bundle(entrega: Entrega | None) -> dict[str, object]:
    pts = entregas_catalog_service.productos_terminados_activos()
    clientes = entregas_catalog_service.clientes_activos()
    choferes = entregas_catalog_service.choferes_activos()
    lugares: list[LugarEntrega] = []
    if entrega and entrega.cliente_id:
        lugares = entregas_catalog_service.lugares_activos_por_cliente(int(entrega.cliente_id))
    lugares_todos = entregas_catalog_service.lugares_activos_todos()
    lugares_catalogo = [
        {"id": int(x.id), "cliente_id": int(x.cliente_id), "nombre": str(x.nombre).strip()} for x in lugares_todos
    ]
    return {
        "productos_terminados": pts,
        "clientes_entrega": clientes,
        "choferes_entrega": choferes,
        "lugares_entrega": lugares,
        "lugares_entrega_catalogo": lugares_catalogo,
    }


def marcas_y_equipo_para_producto_stock(stock_producto: str) -> tuple[list[str], bool]:
    marcas: list[str] = []
    req_eq = False
    if stock_service.producto_entrega_es_stock_hipoclorito(stock_producto):
        cat_key = clave_catalogo_stock_producto_terminado(stock_producto)
        req_eq = stock_service.producto_requiere_equipo(ENTREGAS_STOCK_CATEGORIA, cat_key)
    return marcas, req_eq


def ctx_hipo_operational_programar(exclude_entrega_id: int | None = None) -> dict[str, object]:
    """KPIs informativos en el formulario de programación (no bloquean guardar)."""
    reserved = operational_informed_stock.sum_hipochlorito_programada_liters(exclude_entrega_id)
    avail = operational_informed_stock.operational_liters_available_for_new_programada(exclude_entrega_id)
    return {
        "hipo_ops_reserved_programada_display": operational_informed_stock.format_header_liters(float(reserved)),
        "hipo_ops_avail_programar_display": operational_informed_stock.format_header_liters(float(avail))
        if avail is not None
        else "N/D",
        "hipo_ops_avail_programar_liters": avail,
    }


def get_entrega_for_edit(eid: int) -> Entrega | None:
    return db.session.scalar(
        select(Entrega)
        .options(
            selectinload(Entrega.producto_terminado),
            selectinload(Entrega.cliente_row),
            selectinload(Entrega.lugar_row),
        )
        .where(Entrega.id == eid)
    )


def get_entrega_for_historial(eid: int) -> Entrega | None:
    return get_entrega_for_edit(eid)


def build_historial_event_rows(eid: int) -> list[dict[str, Any]]:
    evs = list(
        db.session.scalars(
            select(EntregaEvento).where(EntregaEvento.entrega_id == eid).order_by(EntregaEvento.id.asc())
        ).all()
    )
    rows: list[dict[str, Any]] = []
    for r in evs:
        det = None
        if r.detalle:
            try:
                det = json.loads(r.detalle)
            except json.JSONDecodeError:
                det = r.detalle
        rows.append({"ev": r, "detalle": det})
    return rows


def api_lugares_rows(cliente_id: int) -> list[dict[str, Any]]:
    lugares = entregas_catalog_service.lugares_activos_por_cliente(cliente_id)
    return [{"id": int(x.id), "nombre": str(x.nombre or "").strip(), "cliente_id": int(x.cliente_id)} for x in lugares]


def api_marcas_producto_terminado_payload(pt_id: int) -> dict[str, Any]:
    pt = db.session.get(ProductoTerminado, pt_id)
    if pt is None or not pt.activo:
        return {"marcas": [], "requiere_equipo": False, "marca_traza_fija": None}
    sp = str(pt.stock_producto or "")
    marcas, req_eq = marcas_y_equipo_para_producto_stock(sp)
    hipo = stock_service.producto_entrega_es_stock_hipoclorito(sp)
    return {
        "marcas": marcas,
        "requiere_equipo": req_eq,
        "marca_traza_fija": (ENTREGAS_MARCA_PRODUCTO_TERMINADO_TRAZA if hipo else None),
    }


def producto_terminado_hipo_default() -> ProductoTerminado | None:
    for pt in entregas_catalog_service.productos_terminados_activos():
        if stock_service.producto_entrega_es_stock_hipoclorito(str(pt.stock_producto or "")):
            return pt
    return None


def create_carga_camion_from_form(form: Any, u: User | None) -> tuple[Entrega, tuple[str, str] | None]:
    """Operaciones: volumen cargado, chofer y fecha automática (hoy). Logística completa destino después."""
    chid = parse_entrega_positive_int(form.get("chofer_entrega_id"))
    cantidad = parse_entrega_float(form.get("cantidad"))
    ptid = parse_entrega_positive_int(form.get("producto_terminado_id"))
    if cantidad <= 0 or cantidad != cantidad:
        raise ValueError("El volumen cargado debe ser un número válido y mayor a cero.")
    if not chid:
        raise ValueError("El chofer es obligatorio.")
    ch = entregas_catalog_service.get_chofer_activo(chid)
    if ch is None:
        raise ValueError("Chofer inválido o inactivo.")
    pt = entregas_catalog_service.get_producto_terminado_activo(ptid) if ptid else producto_terminado_hipo_default()
    if pt is None:
        raise ValueError(
            "No hay producto terminado de hipoclorito activo. Un administrador debe cargarlo en Catálogos de entregas."
        )
    prod_stock = str(pt.stock_producto or "").strip()
    stock_cat, stock_marca, stock_eq = stock_fields_entrega(prod_stock, form.get("stock_equipo_id") or "")
    if stock_service.producto_entrega_es_stock_hipoclorito(prod_stock):
        cat_key = clave_catalogo_stock_producto_terminado(prod_stock)
        if stock_service.producto_requiere_equipo(ENTREGAS_STOCK_CATEGORIA, cat_key) and stock_eq is None:
            raise ValueError("Este producto requiere equipo en el consumo de stock.")
    else:
        stock_cat, stock_marca, stock_eq = None, None, None

    from app.utils.datetime_operacion import now_operacion_naive_local

    ahora = now_operacion_naive_local()
    en = Entrega(
        cliente=ENTREGA_CLIENTE_PENDIENTE_LOGISTICA,
        lugar_entrega=ENTREGA_LUGAR_PENDIENTE_LOGISTICA,
        producto=prod_stock,
        cantidad=cantidad,
        cantidad_programada=cantidad,
        unidad=UNIDAD_ENTREGA,
        fecha_prevista=ahora.date().isoformat(),
        chofer_previsto=str(ch.nombre).strip(),
        estado="programada",
        created_by_user_id=int(u.id) if u else None,
        stock_categoria=stock_cat,
        stock_marca=stock_marca,
        stock_equipo_id=stock_eq,
        producto_terminado_id=int(pt.id),
        chofer_entrega_id=int(ch.id),
    )
    stock_mut = entregas_service.crear_y_ejecutar_carga_camion(en, u, ahora, cantidad)
    return en, stock_mut


def create_programada_entrega_from_form(form: Any, u: User | None) -> Entrega:
    cid = parse_entrega_positive_int(form.get("cliente_id"))
    lid = parse_entrega_positive_int(form.get("lugar_entrega_id"))
    ptid = parse_entrega_positive_int(form.get("producto_terminado_id"))
    chid = parse_entrega_positive_int(form.get("chofer_entrega_id"))
    cantidad = parse_entrega_float(form.get("cantidad"))
    fecha_prev = (form.get("fecha_prevista") or "").strip()
    hora_prev = normalize_hora_prevista(form.get("hora_prevista"))
    obs = (form.get("observaciones") or "").strip() or None
    iso = now_operacion_local_iso_seconds()

    err, cli, lug, pt, ch = validar_entrega_completa(cid, lid, ptid, chid)
    if err:
        raise ValueError(err)
    if cantidad <= 0 or cantidad != cantidad:
        raise ValueError("El volumen en litros debe ser un número válido y mayor a cero.")
    if not fecha_prev:
        raise ValueError("La fecha prevista es obligatoria.")
    if hora_prev:
        obs = f"Hora prevista: {hora_prev}" + (f"\n{obs}" if obs else "")

    prod_stock = str(pt.stock_producto or "").strip()
    hipo = stock_service.producto_entrega_es_stock_hipoclorito(prod_stock)
    stock_cat, stock_marca, stock_eq = stock_fields_entrega(prod_stock, form.get("stock_equipo_id") or "")
    if hipo:
        cat_key = clave_catalogo_stock_producto_terminado(prod_stock)
        if stock_service.producto_requiere_equipo(ENTREGAS_STOCK_CATEGORIA, cat_key) and stock_eq is None:
            raise ValueError("Este producto requiere equipo en el consumo de stock.")
        # Stock operativo: no se valida al programar; solo al confirmar «Cargar» en gestión.
    else:
        stock_cat, stock_marca, stock_eq = None, None, None

    en = Entrega(
        cliente=cli.nombre,
        lugar_entrega=lug.nombre,
        producto=prod_stock,
        cantidad=cantidad,
        cantidad_programada=cantidad,
        unidad=UNIDAD_ENTREGA,
        fecha_prevista=fecha_prev,
        observaciones=obs,
        chofer_previsto=ch.nombre if ch else None,
        estado="programada",
        created_at_iso=iso,
        updated_at_iso=iso,
        created_by_user_id=int(u.id) if u else None,
        stock_categoria=stock_cat,
        stock_marca=stock_marca,
        stock_equipo_id=stock_eq,
        cliente_id=int(cli.id),
        lugar_entrega_id=int(lug.id),
        producto_terminado_id=int(pt.id),
        chofer_entrega_id=int(ch.id) if ch else None,
    )
    db.session.add(en)
    db.session.flush()
    from app.auth_utils import user_display_name

    entregas_service.append_evento(
        int(en.id),
        "creada",
        iso,
        u,
        user_display_name(u),
        {
            "cliente": cli.nombre,
            "producto": prod_stock,
            "cantidad": cantidad,
            "cantidad_programada": cantidad,
            "unidad": UNIDAD_ENTREGA,
            "fecha_prevista": fecha_prev,
            "hora_prevista": hora_prev or None,
        },
    )
    return en


def catalog_post_productos_terminados(form: Any, now_iso: str) -> str:
    act = (form.get("action") or "").strip()
    if act == "nuevo":
        nombre = (form.get("nombre") or "").strip()
        sp = (form.get("stock_producto") or "").strip()
        if not nombre or not sp:
            raise ValueError("Nombre y producto de stock son obligatorios.")
        db.session.add(
            ProductoTerminado(
                nombre=nombre,
                stock_producto=sp,
                activo=True,
                created_at_iso=now_iso,
                updated_at_iso=now_iso,
            )
        )
        db.session.commit()
        return "Producto terminado creado."
    if act == "toggle" and (form.get("id") or "").strip().isdigit():
        row = db.session.get(ProductoTerminado, int(form.get("id")))
        if row:
            row.activo = not bool(row.activo)
            row.updated_at_iso = now_iso
            db.session.commit()
            return "Estado actualizado."
        return ""
    return ""


def catalog_post_clientes(form: Any, now_iso: str) -> str:
    act = (form.get("action") or "").strip()
    if act == "nuevo":
        nombre = (form.get("nombre") or "").strip()
        obs = (form.get("observaciones") or "").strip() or None
        if not nombre:
            raise ValueError("El nombre es obligatorio.")
        db.session.add(
            ClienteEntrega(
                nombre=nombre,
                observaciones=obs,
                activo=True,
                created_at_iso=now_iso,
                updated_at_iso=now_iso,
            )
        )
        db.session.commit()
        return "Cliente creado."
    if act == "toggle" and (form.get("id") or "").strip().isdigit():
        row = db.session.get(ClienteEntrega, int(form.get("id")))
        if row:
            row.activo = not bool(row.activo)
            row.updated_at_iso = now_iso
            db.session.commit()
            return "Estado actualizado."
        return ""
    return ""


def catalog_post_lugares(form: Any, now_iso: str) -> str:
    act = (form.get("action") or "").strip()
    if act == "nuevo":
        nombre = (form.get("nombre") or "").strip()
        cid_raw = (form.get("cliente_id") or "").strip()
        if not nombre or not cid_raw.isdigit():
            raise ValueError("Nombre y cliente son obligatorios.")
        if db.session.get(ClienteEntrega, int(cid_raw)) is None:
            raise ValueError("Cliente no encontrado.")
        db.session.add(
            LugarEntrega(
                nombre=nombre,
                cliente_id=int(cid_raw),
                activo=True,
                created_at_iso=now_iso,
                updated_at_iso=now_iso,
            )
        )
        db.session.commit()
        return "Lugar de entrega creado."
    if act == "toggle" and (form.get("id") or "").strip().isdigit():
        row = db.session.get(LugarEntrega, int(form.get("id")))
        if row:
            row.activo = not bool(row.activo)
            row.updated_at_iso = now_iso
            db.session.commit()
            return "Estado actualizado."
        return ""
    return ""


def catalog_post_choferes(form: Any, now_iso: str) -> str:
    act = (form.get("action") or "").strip()
    if act == "nuevo":
        nombre = (form.get("nombre") or "").strip()
        obs = (form.get("observaciones") or "").strip() or None
        if not nombre:
            raise ValueError("El nombre es obligatorio.")
        db.session.add(
            ChoferEntrega(
                nombre=nombre,
                observaciones=obs,
                activo=True,
                created_at_iso=now_iso,
                updated_at_iso=now_iso,
            )
        )
        db.session.commit()
        return "Chofer creado."
    if act == "toggle" and (form.get("id") or "").strip().isdigit():
        row = db.session.get(ChoferEntrega, int(form.get("id")))
        if row:
            row.activo = not bool(row.activo)
            row.updated_at_iso = now_iso
            db.session.commit()
            return "Estado actualizado."
        return ""
    return ""


def list_productos_terminados_admin() -> list[ProductoTerminado]:
    return list(db.session.scalars(select(ProductoTerminado).order_by(ProductoTerminado.nombre.asc())).all())


def list_clientes_entrega_admin() -> list[ClienteEntrega]:
    return list(db.session.scalars(select(ClienteEntrega).order_by(ClienteEntrega.nombre.asc())).all())


def list_lugares_entrega_admin() -> list[LugarEntrega]:
    return list(
        db.session.scalars(select(LugarEntrega).order_by(LugarEntrega.cliente_id.asc(), LugarEntrega.nombre.asc())).all()
    )


def list_choferes_entrega_admin() -> list[ChoferEntrega]:
    return list(db.session.scalars(select(ChoferEntrega).order_by(ChoferEntrega.nombre.asc())).all())


def gestion_constants_context() -> dict[str, str]:
    return {
        "hipoclorito_nombre_catalogo": HIPOCLORITO_STOCK_NOMBRE_PRODUCTO,
        "entrega_marca_pt_traza": ENTREGAS_MARCA_PRODUCTO_TERMINADO_TRAZA,
    }
