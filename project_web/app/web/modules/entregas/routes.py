from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for

from app.constants import ENTREGAS_STOCK_CATEGORIA
from app.auth_utils import (
    current_user,
    login_required,
    user_can_access_entregas_hub,
    user_can_entregas_cargar_effective,
    user_can_entregas_entregar_effective,
    user_can_entregas_programar_effective,
    user_can_view_admin_configuration,
    user_display_name,
    user_may_view_entregas_programar,
)
from app.extensions import db
from app.models import Entrega, User
from app.security_http import request_path_for_login_next
from app.services import entregas_catalog_service, entregas_service, entregas_web_service as ews, stock_service
from app.services.entregas_service import FiltroHistorialEntregas
from app.utils.datetime_operacion import now_operacion_local_iso_seconds, now_operacion_naive_local
from app.utils.hipoclorito_producto import aliases_entrega_lower_sorted, clave_catalogo_stock_producto_terminado

bp = Blueprint("entregas", __name__, url_prefix="/entregas")


def _entrega_lugares_api_prefix() -> str:
    path = url_for("entregas.api_lugares_por_cliente", cliente_id=0)
    return path.rsplit("/", 1)[0] + "/"


def _entrega_marcas_api_prefix() -> str:
    path = url_for("entregas.api_marcas_producto_terminado", pt_id=0)
    return path.rsplit("/", 1)[0] + "/"


def _filtro_historial_entregas_from_request() -> FiltroHistorialEntregas:
    def _int_or_none(key: str) -> int | None:
        v = (request.args.get(key) or "").strip()
        return int(v) if v.isdigit() else None

    fd = (request.args.get("fecha_desde") or "").strip()
    fh = (request.args.get("fecha_hasta") or "").strip()
    d0: date | None = None
    d1: date | None = None
    if fd:
        try:
            d0 = date.fromisoformat(fd)
        except ValueError:
            d0 = None
    if fh:
        try:
            d1 = date.fromisoformat(fh)
        except ValueError:
            d1 = None
    est = (request.args.get("estado") or "").strip() or None
    return FiltroHistorialEntregas(
        cliente_id=_int_or_none("cliente_id"),
        lugar_entrega_id=_int_or_none("lugar_entrega_id"),
        chofer_entrega_id=_int_or_none("chofer_entrega_id"),
        estado=est,
        fecha_desde=d0,
        fecha_hasta=d1,
    )


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
        if act == "programar_rapido":
            if not user_can_entregas_programar_effective(u):
                return _no_edit()
            try:
                ews.create_programada_entrega_from_form(request.form, u)
                db.session.commit()
                flash("Entrega programada.", "success")
                keep = {
                    "quick_fecha": (request.form.get("fecha_prevista") or "").strip(),
                    "quick_producto_terminado_id": (request.form.get("producto_terminado_id") or "").strip(),
                    "quick_chofer_entrega_id": (request.form.get("chofer_entrega_id") or "").strip(),
                }
                return redirect(url_for("entregas.gestion", **{k: v for k, v in keep.items() if v}))
            except ValueError as ex:
                db.session.rollback()
                flash(str(ex), "danger")
                return redirect(url_for("entregas.gestion"))

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
                programada = entregas_service.cantidad_programada_operativa(ent)
                cantidad_real_raw = request.form.get("cantidad_real")
                cantidad_real = entregas_service.validate_cantidad_real(
                    programada if cantidad_real_raw is None else cantidad_real_raw, "La cantidad a cargar"
                )
                warning = entregas_service.cantidad_real_warning(programada, cantidad_real)
                stock_mut = entregas_service.ejecutar_cargada(ent, u, ahora, cantidad_real)
                db.session.commit()
                if stock_mut is not None:
                    stock_service.after_stock_mutation(stock_mut[0], stock_mut[1])
                flash("Entrega marcada como cargada.", "success")
                if warning:
                    flash(warning, "warning")
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
                programada = entregas_service.cantidad_programada_operativa(ent)
                cantidad_real_raw = request.form.get("cantidad_real")
                cantidad_real = entregas_service.validate_cantidad_real(
                    programada if cantidad_real_raw is None else cantidad_real_raw, "La cantidad a entregar"
                )
                warning = entregas_service.cantidad_real_warning(programada, cantidad_real)
                entregas_service.ejecutar_entregada(ent, u, ahora, cantidad_real)
                db.session.commit()
                flash("Entrega marcada como entregada.", "success")
                if warning:
                    flash(warning, "warning")
            except Exception as ex:  # noqa: BLE001
                db.session.rollback()
                flash(str(ex) or "No se pudo registrar la entrega.", "danger")
            return redirect(url_for("entregas.gestion"))

        flash("Acción no reconocida.", "warning")
        return redirect(url_for("entregas.gestion"))

    rows = entregas_service.listar_entregas()
    entregas_kpis = entregas_service.entregas_kpis_rolling()
    sem_lunes, _sem_domingo = entregas_service.rango_semana_operacion_actual()
    catalog_bundle = ews.form_catalog_bundle(None)
    return render_template(
        "entregas/gestion.html",
        entregas=rows,
        entregas_kpis=entregas_kpis,
        entregas_vista_semana_lunes=sem_lunes,
        quick_fecha=request.args.get("quick_fecha", ""),
        quick_producto_terminado_id=ews.parse_entrega_positive_int(request.args.get("quick_producto_terminado_id")),
        quick_chofer_entrega_id=ews.parse_entrega_positive_int(request.args.get("quick_chofer_entrega_id")),
        entrega_lugares_api_prefix=_entrega_lugares_api_prefix(),
        **catalog_bundle,
        **ews.gestion_constants_context(),
    )


@bp.get("/historial-entregas")
@login_required
def historial_entregas_lista():
    u = current_user()
    if not user_can_access_entregas_hub(u):
        return _no_access()
    filtro = _filtro_historial_entregas_from_request()
    rows = entregas_service.get_historial_entregas_filtrado(filtro)
    exp_qs = urlencode(request.args.to_dict(flat=True))
    return render_template(
        "entregas/historial_lista.html",
        entregas=rows,
        filtro_clientes=entregas_catalog_service.clientes_activos(),
        filtro_lugares=entregas_catalog_service.lugares_activos_todos(),
        filtro_choferes=entregas_catalog_service.choferes_activos(),
        filtro_estados=entregas_service.entregas_estados_para_filtro(),
        filtro_aplicado=filtro,
        historial_export_query=exp_qs,
        **ews.gestion_constants_context(),
    )


@bp.get("/historial-entregas/export.xlsx")
@login_required
def historial_entregas_export_xlsx():
    u = current_user()
    if not user_can_access_entregas_hub(u):
        return _no_access()
    filtro = _filtro_historial_entregas_from_request()
    buf = entregas_service.exportar_historial_entregas_excel(filtro)
    fname = f"historial_entregas_{now_operacion_naive_local().date().isoformat()}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


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
        act = (request.form.get("action") or "").strip()

        if act == "eliminar":
            if not entregas_service.puede_eliminar_entrega(ent):
                flash("No se puede eliminar esta entrega en su estado actual.", "warning")
                return redirect(url_for("entregas.editar", eid=eid))
            try:
                entregas_service.ejecutar_eliminar_entrega(ent)
                db.session.commit()
                flash("Entrega eliminada.", "success")
            except ValueError as ex:
                db.session.rollback()
                flash(str(ex), "danger")
            return redirect(url_for("entregas.gestion"))

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
                # Stock operativo: no se valida al editar programación; solo al confirmar «Cargar».
            else:
                stock_cat, stock_marca, stock_eq = None, None, None

            ews.assign_catalogo_a_entrega(ent, cli, lug, pt, ch)
            ent.cantidad = cantidad
            ent.cantidad_programada = cantidad
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
def catalogos_hub():
    u = current_user()
    if u is None or not user_can_view_admin_configuration(u):
        flash("No tenés permiso para acceder a catálogos de entregas.", "warning")
        return redirect(url_for("entregas.hub"))
    return render_template("entregas/catalogos_hub.html", viewer_may_edit_catalogos=bool(u.is_admin))


@bp.route("/catalogos/productos-terminados", methods=["GET", "POST"])
@login_required
def catalogos_productos():
    u = current_user()
    if u is None:
        return redirect(url_for("auth.login", next=request_path_for_login_next()))
    if request.method == "POST":
        if not u.is_admin:
            flash("Solo administradores pueden modificar catálogos.", "warning")
            return redirect(url_for("entregas.catalogos_productos"))
        now = now_operacion_local_iso_seconds()
        try:
            msg = ews.catalog_post_productos_terminados(request.form, now)
            if msg:
                flash(msg, "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("entregas.catalogos_productos"))

    if not user_can_view_admin_configuration(u):
        flash("No tenés permiso para acceder a catálogos de entregas.", "warning")
        return redirect(url_for("entregas.hub"))

    rows = ews.list_productos_terminados_admin()
    return render_template(
        "entregas/catalogos_productos.html",
        items=rows,
        viewer_may_edit_catalogos=bool(u.is_admin),
    )


@bp.route("/catalogos/clientes", methods=["GET", "POST"])
@login_required
def catalogos_clientes():
    u = current_user()
    if u is None:
        return redirect(url_for("auth.login", next=request_path_for_login_next()))
    if request.method == "POST":
        if not u.is_admin:
            flash("Solo administradores pueden modificar catálogos.", "warning")
            return redirect(url_for("entregas.catalogos_clientes"))
        now = now_operacion_local_iso_seconds()
        try:
            msg = ews.catalog_post_clientes(request.form, now)
            if msg:
                flash(msg, "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("entregas.catalogos_clientes"))

    if not user_can_view_admin_configuration(u):
        flash("No tenés permiso para acceder a catálogos de entregas.", "warning")
        return redirect(url_for("entregas.hub"))

    rows = ews.list_clientes_entrega_admin()
    return render_template(
        "entregas/catalogos_clientes.html",
        items=rows,
        viewer_may_edit_catalogos=bool(u.is_admin),
    )


@bp.route("/catalogos/lugares", methods=["GET", "POST"])
@login_required
def catalogos_lugares():
    u = current_user()
    if u is None:
        return redirect(url_for("auth.login", next=request_path_for_login_next()))
    if request.method == "POST":
        if not u.is_admin:
            flash("Solo administradores pueden modificar catálogos.", "warning")
            return redirect(url_for("entregas.catalogos_lugares"))
        now = now_operacion_local_iso_seconds()
        try:
            msg = ews.catalog_post_lugares(request.form, now)
            if msg:
                flash(msg, "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("entregas.catalogos_lugares"))

    if not user_can_view_admin_configuration(u):
        flash("No tenés permiso para acceder a catálogos de entregas.", "warning")
        return redirect(url_for("entregas.hub"))

    clientes = ews.list_clientes_entrega_admin()
    rows = ews.list_lugares_entrega_admin()
    return render_template(
        "entregas/catalogos_lugares.html",
        items=rows,
        clientes=clientes,
        viewer_may_edit_catalogos=bool(u.is_admin),
    )


@bp.route("/catalogos/choferes", methods=["GET", "POST"])
@login_required
def catalogos_choferes():
    u = current_user()
    if u is None:
        return redirect(url_for("auth.login", next=request_path_for_login_next()))
    if request.method == "POST":
        if not u.is_admin:
            flash("Solo administradores pueden modificar catálogos.", "warning")
            return redirect(url_for("entregas.catalogos_choferes"))
        now = now_operacion_local_iso_seconds()
        try:
            msg = ews.catalog_post_choferes(request.form, now)
            if msg:
                flash(msg, "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("entregas.catalogos_choferes"))

    if not user_can_view_admin_configuration(u):
        flash("No tenés permiso para acceder a catálogos de entregas.", "warning")
        return redirect(url_for("entregas.hub"))

    rows = ews.list_choferes_entrega_admin()
    return render_template(
        "entregas/catalogos_choferes.html",
        items=rows,
        viewer_may_edit_catalogos=bool(u.is_admin),
    )
