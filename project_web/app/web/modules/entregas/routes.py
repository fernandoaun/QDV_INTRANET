from __future__ import annotations

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from app.constants import ENTREGAS_STOCK_CATEGORIA
from app.auth_utils import (
    admin_required,
    current_user,
    login_required,
    user_can_access_entregas_hub,
    user_can_entregas_cargar_effective,
    user_can_entregas_entregar_effective,
    user_can_entregas_programar_effective,
    user_display_name,
    user_may_view_entregas_programar,
)
from app.extensions import db
from app.models import Entrega, User
from app.services import entregas_service, entregas_web_service as ews, stock_service
from app.utils.datetime_operacion import now_operacion_local_iso_seconds, now_operacion_naive_local
from app.utils.hipoclorito_producto import aliases_entrega_lower_sorted, clave_catalogo_stock_producto_terminado

bp = Blueprint("entregas", __name__, url_prefix="/entregas")


def _entrega_lugares_api_prefix() -> str:
    path = url_for("entregas.api_lugares_por_cliente", cliente_id=0)
    return path.rsplit("/", 1)[0] + "/"


def _entrega_marcas_api_prefix() -> str:
    path = url_for("entregas.api_marcas_producto_terminado", pt_id=0)
    return path.rsplit("/", 1)[0] + "/"


def _no_access():
    flash("No tenés permiso para acceder al módulo Entregas.", "warning")
    return redirect(url_for("main.dashboard"))


def _no_edit():
    flash("No tenés permiso de edición para esta acción.", "warning")
    return redirect(request.referrer or url_for("entregas.gestion"))


@bp.get("/")
@login_required
def hub():
    u = current_user()
    if not user_can_access_entregas_hub(u):
        return _no_access()
    return render_template("entregas/hub.html")


@bp.route("/gestion", methods=["GET", "POST"])
@login_required
def gestion():
    u = current_user()
    if not user_can_access_entregas_hub(u):
        return _no_access()

    if request.method == "POST":
        act = (request.form.get("action") or "").strip()
        eid_raw = (request.form.get("entrega_id") or "").strip()
        if not eid_raw.isdigit():
            flash("Solicitud inválida.", "danger")
            return redirect(url_for("entregas.gestion"))
        eid = int(eid_raw)
        ent = db.session.get(Entrega, eid)
        if ent is None:
            flash("Entrega no encontrada.", "danger")
            return redirect(url_for("entregas.gestion"))

        confirm = (request.form.get("confirm") or "").strip() == "1"
        if act == "cargar":
            if not user_can_entregas_cargar_effective(u):
                return _no_edit()
            if not confirm:
                flash("Falta confirmar la acción.", "warning")
                return redirect(url_for("entregas.gestion"))
            try:
                ahora = now_operacion_naive_local()
                entregas_service.ejecutar_cargada(ent, u, ahora)
                db.session.commit()
                flash("Entrega marcada como cargada.", "success")
            except Exception as ex:  # noqa: BLE001
                db.session.rollback()
                flash(str(ex) or "No se pudo registrar la carga.", "danger")
            return redirect(url_for("entregas.gestion"))

        if act == "entregar":
            if not user_can_entregas_entregar_effective(u):
                return _no_edit()
            if not confirm:
                flash("Falta confirmar la acción.", "warning")
                return redirect(url_for("entregas.gestion"))
            try:
                ahora = now_operacion_naive_local()
                entregas_service.ejecutar_entregada(ent, u, ahora)
                db.session.commit()
                flash("Entrega marcada como entregada.", "success")
            except Exception as ex:  # noqa: BLE001
                db.session.rollback()
                flash(str(ex) or "No se pudo registrar la entrega.", "danger")
            return redirect(url_for("entregas.gestion"))

        flash("Acción no reconocida.", "warning")
        return redirect(url_for("entregas.gestion"))

    rows = entregas_service.listar_entregas()
    return render_template("entregas/gestion.html", entregas=rows, **ews.gestion_constants_context())


@bp.get("/api/lugares-por-cliente/<int:cliente_id>")
@login_required
def api_lugares_por_cliente(cliente_id: int):
    u = current_user()
    if not user_can_access_entregas_hub(u):
        return jsonify({"lugares": [], "error": "forbidden"}), 403
    rows = ews.api_lugares_rows(cliente_id)
    if request.args.get("dbg_entregas") == "1":
        current_app.logger.info("api_lugares_por_cliente cliente_id=%s count=%s", cliente_id, len(rows))
    return jsonify({"lugares": rows})


@bp.get("/api/marcas-producto-terminado/<int:pt_id>")
@login_required
def api_marcas_producto_terminado(pt_id: int):
    u = current_user()
    if not user_can_access_entregas_hub(u):
        return jsonify({"marcas": [], "requiere_equipo": False}), 403
    return jsonify(ews.api_marcas_producto_terminado_payload(pt_id))


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u = current_user()
    if not user_can_access_entregas_hub(u):
        return _no_access()
    if not user_may_view_entregas_programar(u):
        return _no_access()
    if request.method == "POST" and not user_can_entregas_programar_effective(u):
        return _no_edit()

    bundle = ews.form_catalog_bundle(None)
    pts = list(bundle["productos_terminados"])  # type: ignore[arg-type]
    selected_pt = pts[0] if pts else None

    marcas: list[str] = []
    req_eq = False
    if selected_pt:
        marcas, req_eq = ews.marcas_y_equipo_para_producto_stock(str(selected_pt.stock_producto or ""))

    equipos = stock_service.equipos_activos()

    if request.method == "POST":
        try:
            ews.create_programada_entrega_from_form(request.form, u)
            db.session.commit()
            flash("Entrega programada.", "success")
            return redirect(url_for("entregas.gestion"))
        except ValueError as ex:
            db.session.rollback()
            flash(str(ex), "danger")
            return redirect(url_for("entregas.nueva"))

    if request.method == "GET":
        if not bundle["productos_terminados"]:
            flash(
                "No hay productos terminados activos. Un administrador debe cargarlos en Catálogos de entregas.",
                "warning",
            )
        if not bundle["clientes_entrega"]:
            flash("No hay clientes activos. Un administrador debe cargarlos en Catálogos de entregas.", "warning")

    stock_traza_hipo_server_visible = bool(
        selected_pt and stock_service.producto_entrega_es_stock_hipoclorito(str(selected_pt.stock_producto or ""))
    )

    ctx = {
        **bundle,
        **ews.ctx_hipo_operational_programar(None),
        "entrega": None,
        "marcas": marcas,
        "equipos": equipos,
        "producto_requiere_equipo": req_eq,
        "stock_traza_hipo_server_visible": stock_traza_hipo_server_visible,
        "hipoclorito_entrega_aliases_lower": aliases_entrega_lower_sorted(),
        "selected_producto_terminado_id": int(selected_pt.id) if selected_pt else None,
        "entrega_lugares_api_prefix": _entrega_lugares_api_prefix(),
        "entrega_marcas_api_prefix": _entrega_marcas_api_prefix(),
        **ews.gestion_constants_context(),
    }
    return render_template("entregas/form.html", **ctx)


@bp.route("/<int:eid>/editar", methods=["GET", "POST"])
@login_required
def editar(eid: int):
    u = current_user()
    if not user_can_access_entregas_hub(u):
        return _no_access()

    ent = ews.get_entrega_for_edit(eid)
    if ent is None:
        flash("Entrega no encontrada.", "danger")
        return redirect(url_for("entregas.gestion"))

    if request.method == "POST":
        estado = str(ent.estado or "")
        if estado == "entregada":
            if not user_can_entregas_programar_effective(u):
                return _no_edit()
        elif entregas_service.puede_editar_logistica_tras_carga(ent):
            if not user_can_entregas_programar_effective(u) and not user_can_entregas_cargar_effective(u):
                return _no_edit()
        elif not user_can_entregas_programar_effective(u):
            return _no_edit()

    iso = now_operacion_local_iso_seconds()

    is_hipo = stock_service.producto_entrega_es_stock_hipoclorito(ent.producto or "")
    marcas: list[str] = []
    req_eq = False
    if is_hipo and entregas_service.puede_editar_campos_completos(ent):
        prod = (ent.producto or "").strip()
        if prod:
            marcas, req_eq = ews.marcas_y_equipo_para_producto_stock(prod)
    equipos = stock_service.equipos_activos()

    if request.method == "POST":
        estado = str(ent.estado or "")

        if estado == "entregada":
            obs_new = (request.form.get("observaciones") or "").strip()
            if obs_new:
                prev = (ent.observaciones or "").strip()
                ent.observaciones = (prev + "\n" if prev else "") + obs_new
            ent.updated_at_iso = iso
            entregas_service.append_evento(
                int(ent.id),
                "editada",
                iso,
                u,
                user_display_name(u),
                {"nota": "Observaciones (entrega cerrada)", "agregado": obs_new},
            )
            db.session.commit()
            flash("Cambios guardados.", "success")
            return redirect(url_for("entregas.gestion"))

        if entregas_service.puede_editar_campos_completos(ent):
            cid = ews.parse_entrega_positive_int(request.form.get("cliente_id"))
            lid = ews.parse_entrega_positive_int(request.form.get("lugar_entrega_id"))
            ptid = ews.parse_entrega_positive_int(request.form.get("producto_terminado_id"))
            chid = ews.parse_entrega_positive_int(request.form.get("chofer_entrega_id"))
            cantidad = ews.parse_entrega_float(request.form.get("cantidad"))
            fecha_prev = (request.form.get("fecha_prevista") or "").strip()
            obs = (request.form.get("observaciones") or "").strip() or None

            err, cli, lug, pt, ch = ews.validar_entrega_completa(cid, lid, ptid, chid)
            if err:
                flash(err, "danger")
                return redirect(url_for("entregas.editar", eid=eid))
            if cantidad <= 0 or cantidad != cantidad:
                flash("El volumen en litros debe ser un número válido y mayor a cero.", "danger")
                return redirect(url_for("entregas.editar", eid=eid))
            if not fecha_prev:
                flash("La fecha prevista es obligatoria.", "danger")
                return redirect(url_for("entregas.editar", eid=eid))

            prod_stock = str(pt.stock_producto or "").strip()
            hipo = stock_service.producto_entrega_es_stock_hipoclorito(prod_stock)
            stock_cat, stock_marca, stock_eq = ews.stock_fields_entrega(
                prod_stock, request.form.get("stock_equipo_id") or ""
            )
            if hipo:
                cat_key = clave_catalogo_stock_producto_terminado(prod_stock)
                if stock_service.producto_requiere_equipo(ENTREGAS_STOCK_CATEGORIA, cat_key) and stock_eq is None:
                    flash("Este producto requiere equipo.", "danger")
                    return redirect(url_for("entregas.editar", eid=eid))
                try:
                    entregas_service.validar_hipochlorito_cantidad_vs_stock_operativo_panel(
                        cantidad, exclude_entrega_id=int(ent.id)
                    )
                except ValueError as ex:
                    flash(str(ex), "danger")
                    return redirect(url_for("entregas.editar", eid=eid))
            else:
                stock_cat, stock_marca, stock_eq = None, None, None

            ews.assign_catalogo_a_entrega(ent, cli, lug, pt, ch)
            ent.cantidad = cantidad
            ent.fecha_prevista = fecha_prev
            ent.observaciones = obs
            ent.stock_categoria = stock_cat
            ent.stock_marca = stock_marca
            ent.stock_equipo_id = stock_eq
            ent.updated_at_iso = iso
            entregas_service.append_evento(int(ent.id), "editada", iso, u, user_display_name(u), {})
            db.session.commit()
            flash("Entrega actualizada.", "success")
            return redirect(url_for("entregas.gestion"))

        if entregas_service.puede_editar_logistica_tras_carga(ent):
            cid = ews.parse_entrega_positive_int(request.form.get("cliente_id"))
            lid = ews.parse_entrega_positive_int(request.form.get("lugar_entrega_id"))
            chid = ews.parse_entrega_positive_int(request.form.get("chofer_entrega_id"))
            fecha_prev = (request.form.get("fecha_prevista") or "").strip()
            obs = (request.form.get("observaciones") or "").strip() or None

            err, cli, lug, ch = ews.validar_solo_logistica(cid, lid, chid)
            if err:
                flash(err, "danger")
                return redirect(url_for("entregas.editar", eid=eid))
            if not fecha_prev:
                flash("La fecha prevista es obligatoria.", "danger")
                return redirect(url_for("entregas.editar", eid=eid))

            ews.assign_logistica_entrega(ent, cli, lug, ch)
            ent.fecha_prevista = fecha_prev
            ent.observaciones = obs
            ent.updated_at_iso = iso
            entregas_service.append_evento(
                int(ent.id),
                "editada",
                iso,
                u,
                user_display_name(u),
                {"alcance": "logística (estado cargada)"},
            )
            db.session.commit()
            flash("Cambios guardados.", "success")
            return redirect(url_for("entregas.gestion"))

        flash("No se puede editar esta entrega en su estado actual.", "warning")
        return redirect(url_for("entregas.gestion"))

    creador = db.session.get(User, ent.created_by_user_id) if ent.created_by_user_id else None
    stock_traza_hipo_server_visible = bool(is_hipo and entregas_service.puede_editar_campos_completos(ent))
    ctx = {
        **ews.form_catalog_bundle(ent),
        **(
            ews.ctx_hipo_operational_programar(int(ent.id))
            if is_hipo and entregas_service.puede_editar_campos_completos(ent)
            else ews.ctx_hipo_operational_programar(None)
        ),
        "entrega": ent,
        "marcas": marcas,
        "equipos": equipos,
        "producto_requiere_equipo": req_eq,
        "stock_traza_hipo_server_visible": stock_traza_hipo_server_visible,
        "creador_display": user_display_name(creador) if creador else "",
        "hipoclorito_entrega_aliases_lower": aliases_entrega_lower_sorted(),
        "selected_producto_terminado_id": int(ent.producto_terminado_id) if ent.producto_terminado_id else None,
        "entrega_lugares_api_prefix": _entrega_lugares_api_prefix(),
        "entrega_marcas_api_prefix": _entrega_marcas_api_prefix(),
        **ews.gestion_constants_context(),
    }
    return render_template("entregas/form.html", **ctx)


@bp.get("/<int:eid>/historial")
@login_required
def historial(eid: int):
    u = current_user()
    if not user_can_access_entregas_hub(u):
        return _no_access()
    ent = ews.get_entrega_for_historial(eid)
    if ent is None:
        flash("Entrega no encontrada.", "danger")
        return redirect(url_for("entregas.gestion"))
    rows = ews.build_historial_event_rows(eid)
    return render_template("entregas/historial.html", entrega=ent, eventos=rows)


@bp.get("/catalogos")
@login_required
@admin_required
def catalogos_hub():
    return render_template("entregas/catalogos_hub.html")


@bp.route("/catalogos/productos-terminados", methods=["GET", "POST"])
@login_required
@admin_required
def catalogos_productos():
    if request.method == "POST":
        now = now_operacion_local_iso_seconds()
        try:
            msg = ews.catalog_post_productos_terminados(request.form, now)
            if msg:
                flash(msg, "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("entregas.catalogos_productos"))

    rows = ews.list_productos_terminados_admin()
    return render_template("entregas/catalogos_productos.html", items=rows)


@bp.route("/catalogos/clientes", methods=["GET", "POST"])
@login_required
@admin_required
def catalogos_clientes():
    if request.method == "POST":
        now = now_operacion_local_iso_seconds()
        try:
            msg = ews.catalog_post_clientes(request.form, now)
            if msg:
                flash(msg, "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("entregas.catalogos_clientes"))

    rows = ews.list_clientes_entrega_admin()
    return render_template("entregas/catalogos_clientes.html", items=rows)


@bp.route("/catalogos/lugares", methods=["GET", "POST"])
@login_required
@admin_required
def catalogos_lugares():
    clientes = ews.list_clientes_entrega_admin()
    if request.method == "POST":
        now = now_operacion_local_iso_seconds()
        try:
            msg = ews.catalog_post_lugares(request.form, now)
            if msg:
                flash(msg, "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("entregas.catalogos_lugares"))

    rows = ews.list_lugares_entrega_admin()
    return render_template("entregas/catalogos_lugares.html", items=rows, clientes=clientes)


@bp.route("/catalogos/choferes", methods=["GET", "POST"])
@login_required
@admin_required
def catalogos_choferes():
    if request.method == "POST":
        now = now_operacion_local_iso_seconds()
        try:
            msg = ews.catalog_post_choferes(request.form, now)
            if msg:
                flash(msg, "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("entregas.catalogos_choferes"))

    rows = ews.list_choferes_entrega_admin()
    return render_template("entregas/catalogos_choferes.html", items=rows)
