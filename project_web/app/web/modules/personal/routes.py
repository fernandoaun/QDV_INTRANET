from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth_utils import (
    current_user,
    login_required,
    user_can_access_personal,
    user_can_manage_personal,
    user_can_register_entregas_personal,
    user_display_name,
)
from app.extensions import db
from app.models import Operador, PersonalApercibimiento, PersonalCurso
from app.services import personal_service as ps

bp = Blueprint("personal", __name__, url_prefix="/personal")


def _no_access():
    flash("No tenés permiso para acceder a Personal.", "warning")
    return redirect(url_for("main.dashboard"))


def _no_manage():
    flash("Solo RRHH/administrador puede modificar datos de Personal.", "warning")
    return redirect(request.referrer or url_for("personal.hub"))


def _no_register_entregas():
    flash("No tenés permiso para registrar entregas de ropa/EPP.", "warning")
    return redirect(request.referrer or url_for("personal.epp_entregas"))


def _require_view():
    u = current_user()
    if not user_can_access_personal(u):
        return None, _no_access()
    return u, None


def _require_register_entregas(u):
    if not user_can_register_entregas_personal(u):
        return _no_register_entregas()
    return None


def _require_manage(u):
    if not user_can_manage_personal(u):
        return _no_manage()
    return None


@bp.get("/")
@login_required
def hub():
    u, redir = _require_view()
    if redir is not None:
        return redir
    ps.sync_empleados_from_users()
    return render_template(
        "personal/hub.html",
        counts=ps.dashboard_counts(),
        cumpleanos=ps.proximos_cumpleanos(30),
        puede_gestionar=user_can_manage_personal(u),
    )


@bp.get("/legajos")
@login_required
def legajos():
    u, redir = _require_view()
    if redir is not None:
        return redir
    return render_template(
        "personal/legajos.html",
        empleados=ps.list_empleados(q=request.args.get("q", ""), estado=request.args.get("estado", "")),
        legajo_status=ps.legajo_status_by_empleado_id(sync_users=False),
        filtros={"q": request.args.get("q", ""), "estado": request.args.get("estado", "")},
        estado_labels=ps.ESTADO_EMPLEADO_LABELS,
        puede_gestionar=user_can_manage_personal(u),
    )


@bp.route("/legajos/nuevo", methods=["GET", "POST"])
@login_required
def legajo_nuevo():
    flash("Los legajos se crean al dar de alta un usuario en Administración. Desde acá podés completar el perfil.", "info")
    return redirect(url_for("personal.legajos"))


@bp.route("/legajos/usuario/<int:user_id>", methods=["GET", "POST"])
@login_required
def legajo_por_usuario(user_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    from app.models import User

    user = db.session.get(User, user_id)
    if user is None:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("personal.legajos"))
    if not ps.user_requires_legajo(user):
        flash("Los perfiles Angel y SGI no llevan legajo RRHH.", "info")
        return redirect(url_for("personal.legajos"))
    emp = ps.ensure_empleado_for_user(user)
    if emp is None:
        flash("No se pudo abrir el legajo para este usuario.", "warning")
        return redirect(url_for("personal.legajos"))
    return redirect(url_for("personal.legajo_detalle", empleado_id=emp.id))


@bp.route("/legajos/<int:empleado_id>", methods=["GET", "POST"])
@login_required
def legajo_detalle(empleado_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    emp = ps.get_empleado(empleado_id)
    if emp is None:
        flash("Legajo no encontrado.", "danger")
        return redirect(url_for("personal.legajos"))

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        if action == "entrega_epp":
            rredir = _require_register_entregas(u)
            if rredir is not None:
                return rredir
        else:
            mredir = _require_manage(u)
            if mredir is not None:
                return mredir
        ok, msg = False, "Acción no reconocida."
        if action == "legajo":
            ok, msg, _ = ps.save_empleado(request.form, empleado_id=empleado_id, user_id=u.id)
        elif action == "curso":
            ok, msg = ps.save_curso(empleado_id, request.form)
        elif action == "apercibimiento":
            ok, msg = ps.save_apercibimiento(empleado_id, request.form, registrado_por=user_display_name(u))
        elif action == "art":
            ok, msg = ps.save_art(empleado_id, request.form)
        elif action == "entrega_epp":
            data = dict(request.form)
            data["empleado_id"] = str(empleado_id)
            ok, msg = ps.save_entrega_epp(data, user_id=u.id)
        elif action == "vacacion":
            data = dict(request.form)
            data["empleado_id"] = str(empleado_id)
            vac_id_raw = (request.form.get("vacacion_id") or "").strip()
            vac_id = int(vac_id_raw) if vac_id_raw.isdigit() else None
            ok, msg = ps.save_vacacion(data, vacacion_id=vac_id)
        elif action == "vacacion_tomada":
            vac_id_raw = (request.form.get("vacacion_id") or "").strip()
            if vac_id_raw.isdigit():
                ok, msg = ps.marcar_vacacion_tomada(int(vac_id_raw))
        flash(msg, "success" if ok else "danger")
        return redirect(url_for("personal.legajo_detalle", empleado_id=empleado_id, tab=request.form.get("tab") or ""))

    tab = (request.args.get("tab") or "datos").strip()
    if tab == "epp":
        if ps.ensure_default_epp_catalog() > 0:
            flash("Se cargó el catálogo inicial de ropa y EPP. Podés ajustarlo en Catálogo EPP.", "info")
    return render_template(
        "personal/legajo_detalle.html",
        empleado=emp,
        tab=tab,
        operadores=db.session.query(Operador).order_by(Operador.nombre).all(),
        items_epp=ps.list_epp_items(solo_activos=True),
        entregas=ps.list_entregas_epp(empleado_id=empleado_id),
        cursos=emp.cursos.order_by(PersonalCurso.fecha_vencimiento.asc().nullslast(), PersonalCurso.nombre).all(),
        apercibimientos=emp.apercibimientos.order_by(PersonalApercibimiento.fecha.desc()).all(),
        vacaciones=ps.list_vacaciones(empleado_id=empleado_id),
        estado_labels=ps.ESTADO_EMPLEADO_LABELS,
        estado_vacacion_labels=ps.ESTADO_VACACION_LABELS,
        tipo_apercibimiento_labels=ps.TIPO_APERCIBIMIENTO_LABELS,
        categoria_epp_labels=ps.CATEGORIA_EPP_LABELS,
        estado_entrega_labels=ps.ESTADO_ENTREGA_EPP_LABELS,
        puede_gestionar=user_can_manage_personal(u),
        puede_registrar_entregas=user_can_register_entregas_personal(u),
        es_mi_legajo=False,
    )


@bp.route("/legajos/<int:empleado_id>/editar", methods=["GET", "POST"])
@login_required
def legajo_editar(empleado_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    emp = ps.get_empleado(empleado_id)
    if emp is None:
        flash("Legajo no encontrado.", "danger")
        return redirect(url_for("personal.legajos"))
    if request.method == "POST":
        mredir = _require_manage(u)
        if mredir is not None:
            return mredir
        ok, msg, _ = ps.save_empleado(request.form, empleado_id=empleado_id, user_id=u.id)
        flash(msg, "success" if ok else "danger")
        if ok:
            return redirect(url_for("personal.legajo_detalle", empleado_id=empleado_id))
    return render_template(
        "personal/legajo_form.html",
        empleado=emp,
        operadores=db.session.query(Operador).order_by(Operador.nombre).all(),
        estado_labels=ps.ESTADO_EMPLEADO_LABELS,
    )


@bp.route("/epp/catalogo", methods=["GET", "POST"])
@login_required
def epp_catalogo():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if request.method == "POST":
        mredir = _require_manage(u)
        if mredir is not None:
            return mredir
        item_id_raw = (request.form.get("item_id") or "").strip()
        item_id = int(item_id_raw) if item_id_raw.isdigit() else None
        ok, msg = ps.save_epp_item(request.form, item_id=item_id)
        flash(msg, "success" if ok else "danger")
        return redirect(url_for("personal.epp_catalogo"))
    return render_template(
        "personal/epp_catalogo.html",
        items=ps.list_epp_items(),
        categoria_labels=ps.CATEGORIA_EPP_LABELS,
        puede_gestionar=user_can_manage_personal(u),
    )


@bp.route("/epp/entregas", methods=["GET", "POST"])
@login_required
def epp_entregas():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if request.method == "POST":
        rredir = _require_register_entregas(u)
        if rredir is not None:
            return rredir
        ok, msg = ps.save_entrega_epp(request.form, user_id=u.id)
        flash(msg, "success" if ok else "danger")
        return redirect(url_for("personal.epp_entregas"))
    seeded = ps.ensure_default_epp_catalog()
    if seeded > 0:
        flash("Se cargó el catálogo inicial de ropa y EPP. Podés ajustarlo en Catálogo EPP.", "info")
    emp_id_raw = (request.args.get("empleado_id") or "").strip()
    emp_id = int(emp_id_raw) if emp_id_raw.isdigit() else None
    empleados = ps.list_empleados(estado="activo")
    items = ps.list_epp_items(solo_activos=True)
    if not empleados:
        flash("No hay empleados activos con legajo. Los legajos se crean al dar de alta usuarios.", "warning")
    elif not items:
        flash("No hay ítems activos en el catálogo. Cargalos en Catálogo ropa / EPP.", "warning")
    return render_template(
        "personal/epp_entregas.html",
        entregas=ps.list_entregas_epp(empleado_id=emp_id),
        empleados=empleados,
        items=items,
        filtro_empleado_id=emp_id,
        categoria_labels=ps.CATEGORIA_EPP_LABELS,
        estado_entrega_labels=ps.ESTADO_ENTREGA_EPP_LABELS,
        puede_gestionar=user_can_manage_personal(u),
        puede_registrar_entregas=user_can_register_entregas_personal(u),
    )


@bp.route("/mis-entregas-epp", methods=["GET", "POST"])
@login_required
def mis_entregas_epp():
    u = current_user()
    emp = ps.get_empleado_by_user_id(u.id)
    if emp is None:
        flash("No tenés un legajo de personal vinculado a tu usuario.", "warning")
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        entrega_id_raw = (request.form.get("entrega_id") or "").strip()
        if not entrega_id_raw.isdigit():
            flash("Entrega no válida.", "danger")
            return redirect(url_for("personal.mis_entregas_epp"))
        if (request.form.get("confirmar_recepcion") or "").strip() != "1":
            flash("Debés confirmar que recibiste la prenda y devolviste la anterior (si correspondía).", "warning")
            return redirect(url_for("personal.mis_entregas_epp"))
        ok, msg = ps.confirmar_entrega_epp(int(entrega_id_raw), user_id=u.id)
        flash(msg, "success" if ok else "danger")
        return redirect(url_for("personal.mis_entregas_epp"))

    return render_template(
        "personal/mis_entregas_epp.html",
        empleado=emp,
        pendientes=ps.list_entregas_epp_pendientes_empleado(emp.id),
        historial=ps.list_entregas_epp(empleado_id=emp.id, limit=50),
        estado_entrega_labels=ps.ESTADO_ENTREGA_EPP_LABELS,
    )


@bp.get("/mi-legajo")
@login_required
def mi_legajo():
    u = current_user()
    emp = ps.get_empleado_by_user_id(u.id)
    if emp is None:
        flash("No tenés un legajo de personal vinculado a tu usuario.", "warning")
        return redirect(url_for("main.dashboard"))

    tab = (request.args.get("tab") or "datos").strip()
    return render_template(
        "personal/legajo_detalle.html",
        empleado=emp,
        tab=tab,
        operadores=[],
        items_epp=ps.list_epp_items(solo_activos=True),
        entregas=ps.list_entregas_epp(empleado_id=emp.id),
        cursos=emp.cursos.order_by(PersonalCurso.fecha_vencimiento.asc().nullslast(), PersonalCurso.nombre).all(),
        apercibimientos=emp.apercibimientos.order_by(PersonalApercibimiento.fecha.desc()).all(),
        vacaciones=ps.list_vacaciones(empleado_id=emp.id),
        estado_labels=ps.ESTADO_EMPLEADO_LABELS,
        estado_vacacion_labels=ps.ESTADO_VACACION_LABELS,
        tipo_apercibimiento_labels=ps.TIPO_APERCIBIMIENTO_LABELS,
        categoria_epp_labels=ps.CATEGORIA_EPP_LABELS,
        estado_entrega_labels=ps.ESTADO_ENTREGA_EPP_LABELS,
        puede_gestionar=False,
        puede_registrar_entregas=False,
        es_mi_legajo=True,
    )


@bp.route("/vacaciones", methods=["GET", "POST"])
@login_required
def vacaciones():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if request.method == "POST":
        mredir = _require_manage(u)
        if mredir is not None:
            return mredir
        action = (request.form.get("action") or "").strip()
        if action == "marcar_tomada":
            vac_id_raw = (request.form.get("vacacion_id") or "").strip()
            if vac_id_raw.isdigit():
                ok, msg = ps.marcar_vacacion_tomada(int(vac_id_raw))
                flash(msg, "success" if ok else "danger")
        else:
            vac_id_raw = (request.form.get("vacacion_id") or "").strip()
            vac_id = int(vac_id_raw) if vac_id_raw.isdigit() else None
            ok, msg = ps.save_vacacion(request.form, vacacion_id=vac_id)
            flash(msg, "success" if ok else "danger")
        return redirect(url_for("personal.vacaciones", **request.args))

    estado = (request.args.get("estado") or "").strip()
    anio_raw = (request.args.get("anio") or "").strip()
    anio = int(anio_raw) if anio_raw.isdigit() else None
    return render_template(
        "personal/vacaciones.html",
        vacaciones=ps.list_vacaciones(estado=estado, anio=anio),
        empleados=ps.list_empleados(estado="activo"),
        filtros={"estado": estado, "anio": anio_raw},
        estado_labels=ps.ESTADO_VACACION_LABELS,
        puede_gestionar=user_can_manage_personal(u),
    )
