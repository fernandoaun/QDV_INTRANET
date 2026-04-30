from __future__ import annotations

from datetime import date
from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

from app.auth_utils import current_user, login_required, user_can, user_can_access_mantenimiento, user_can_edit
from app.extensions import db
from app.models import Equipo, MaintenanceAttachment, MaintenanceOrder, MaintenancePlan, MaintenancePrediction, MaintenanceFailure
from app.services import mantenimiento_service as ms

bp = Blueprint("mantenimiento", __name__, url_prefix="/mantenimiento")


def _no_access():
    flash("No tenés permiso para acceder a Mantenimiento.", "warning")
    return redirect(url_for("main.dashboard"))


def _no_edit():
    flash("Tenés acceso de solo lectura en Mantenimiento.", "warning")
    return redirect(request.referrer or url_for("mantenimiento.hub"))


def _require_view():
    u = current_user()
    if not user_can_access_mantenimiento(u):
        return None, _no_access()
    return u, None


def _require_edit(u, perm: str):
    if not user_can_edit(u, perm):
        return _no_edit()
    return None


def _can_view_equipos(u) -> bool:
    return user_can(u, "mantenimiento") or user_can(u, "mantenimiento_equipos")


def _can_view_correctivos(u) -> bool:
    return user_can(u, "mantenimiento") or user_can(u, "mantenimiento_correctivos")


def _can_view_preventivos(u) -> bool:
    return user_can(u, "mantenimiento") or user_can(u, "mantenimiento_preventivos")


def _can_view_recursos(u) -> bool:
    return user_can(u, "mantenimiento") or user_can(u, "mantenimiento_recursos")


def _can_view_predictivo(u) -> bool:
    return user_can(u, "mantenimiento") or user_can(u, "mantenimiento_predictivo")


def _components_by_equipo():
    equipos = ms.list_equipos_activos()
    return equipos, {int(e.id): ms.list_components_for_equipo(int(e.id)) for e in equipos}


@bp.get("/")
@login_required
def hub():
    u, redir = _require_view()
    if redir is not None:
        return redir
    return render_template(
        "mantenimiento/hub.html",
        counts=ms.dashboard_counts(),
        top_equipos=ms.top_failures_by_equipo(),
        top_componentes=ms.top_failures_by_component(),
        estados=ms.order_counts_by_estado(),
        criticidades_ordenes=ms.order_counts_by_criticidad(),
        can_view_equipos=_can_view_equipos(u),
        can_view_correctivos=_can_view_correctivos(u),
        can_view_preventivos=_can_view_preventivos(u),
        can_view_predictivo=_can_view_predictivo(u),
    )


@bp.get("/equipos")
@login_required
def equipos():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_equipos(u):
        return _no_access()
    return render_template("mantenimiento/equipos.html", equipos=ms.list_equipos(), **ms.labels_context())


@bp.route("/equipos/<int:equipo_id>", methods=["GET", "POST"])
@login_required
def equipo_detalle(equipo_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_equipos(u):
        return _no_access()
    equipo = db.session.get(Equipo, equipo_id)
    if equipo is None:
        flash("Equipo no encontrado.", "danger")
        return redirect(url_for("mantenimiento.equipos"))
    if request.method == "POST":
        edit_redir = _require_edit(u, "mantenimiento_equipos")
        if edit_redir is not None:
            return edit_redir
        action = (request.form.get("action") or "").strip()
        try:
            if action == "equipo":
                ms.update_equipo_from_form(equipo, request.form)
                db.session.commit()
                flash("Datos del equipo actualizados.", "success")
            elif action == "component":
                ms.create_component_from_form(equipo, request.form)
                db.session.commit()
                flash("Componente asociado creado.", "success")
            else:
                flash("Acción no reconocida.", "warning")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        return redirect(url_for("mantenimiento.equipo_detalle", equipo_id=equipo_id))

    filtros = ms.CorrectivoFiltros(equipo_id=equipo_id)
    return render_template(
        "mantenimiento/equipo_detalle.html",
        equipo=equipo,
        equipos=ms.list_equipos(),
        components=ms.list_components_for_equipo(equipo_id),
        failures=ms.list_failures(filtros, limit=100),
        orders=ms.list_orders(ms.OrdenFiltros(equipo_id=equipo_id), limit=100),
        predictions=[p for p in ms.list_predictions() if int(p.equipo_id) == int(equipo_id)],
        **ms.labels_context(),
    )


@bp.route("/reportar-falla", methods=["GET", "POST"])
@login_required
def reportar():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_correctivos(u):
        return _no_access()
    if request.method == "POST":
        edit_redir = _require_edit(u, "mantenimiento_correctivos")
        if edit_redir is not None:
            return edit_redir
        try:
            failure = ms.create_failure_from_form(request.form, u)
            db.session.flush()
            ms.save_failure_attachment(failure, request.files.get("adjunto"), u)
            db.session.commit()
            flash("Falla correctiva reportada.", "success")
            return redirect(url_for("mantenimiento.failure_detail", failure_id=failure.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    equipos = ms.list_equipos_activos()
    return render_template(
        "mantenimiento/reportar_falla.html",
        equipos=equipos,
        components={int(e.id): ms.list_components_for_equipo(int(e.id)) for e in equipos},
        now_value=ms.current_datetime_input_value(),
        users=ms.list_users_for_responsable(),
        **ms.labels_context(),
    )


@bp.get("/correctivos")
@login_required
def correctivos():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_correctivos(u):
        return _no_access()
    filtros = ms.parse_correctivo_filtros(request.args)
    return render_template(
        "mantenimiento/correctivos.html",
        rows=ms.list_failures(filtros),
        filtros=filtros,
        equipos=ms.list_equipos(),
        users=ms.list_users_for_responsable(),
        export_query=request.query_string.decode("utf-8"),
        **ms.labels_context(),
    )


@bp.get("/correctivos/export.xlsx")
@login_required
def correctivos_export():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_correctivos(u):
        return _no_access()
    filtros = ms.parse_correctivo_filtros(request.args)
    data = ms.export_correctivos_xlsx(ms.list_failures(filtros, limit=None))
    fn = f"mantenimiento_correctivos_{date.today().isoformat()}.xlsx"
    return send_file(
        BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=fn,
    )


@bp.route("/preventivos", methods=["GET", "POST"])
@login_required
def preventivos():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_preventivos(u):
        return _no_access()
    if request.method == "POST":
        edit_redir = _require_edit(u, "mantenimiento_preventivos")
        if edit_redir is not None:
            return edit_redir
        try:
            plan = ms.create_plan_from_form(request.form)
            db.session.commit()
            flash("Plan preventivo creado.", "success")
            return redirect(url_for("mantenimiento.plan_detail", plan_id=plan.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    equipos, components = _components_by_equipo()
    return render_template(
        "mantenimiento/preventivos.html",
        plans=ms.list_plans(),
        equipos=equipos,
        components=components,
        users=ms.list_users_for_responsable(),
        plan_status=ms.plan_status,
        **ms.labels_context(),
    )


@bp.route("/preventivos/<int:plan_id>", methods=["GET", "POST"])
@login_required
def plan_detail(plan_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_preventivos(u):
        return _no_access()
    plan = db.session.get(MaintenancePlan, plan_id)
    if plan is None:
        flash("Plan preventivo no encontrado.", "danger")
        return redirect(url_for("mantenimiento.preventivos"))
    if request.method == "POST":
        edit_redir = _require_edit(u, "mantenimiento_preventivos")
        if edit_redir is not None:
            return edit_redir
        action = (request.form.get("action") or "save").strip()
        try:
            if action == "program":
                order = ms.create_order_from_plan(plan, request.form.get("fecha_programada"))
                db.session.commit()
                flash("Mantenimiento programado desde el plan.", "success")
                return redirect(url_for("mantenimiento.order_detail", order_id=order.id))
            ms.update_plan_from_form(plan, request.form)
            db.session.commit()
            flash("Plan preventivo actualizado.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        return redirect(url_for("mantenimiento.plan_detail", plan_id=plan_id))
    equipos, components = _components_by_equipo()
    return render_template(
        "mantenimiento/plan_detalle.html",
        plan=plan,
        equipos=equipos,
        components=components,
        users=ms.list_users_for_responsable(),
        plan_status=ms.plan_status(plan),
        **ms.labels_context(),
    )


@bp.route("/ordenes", methods=["GET", "POST"])
@login_required
def ordenes():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_preventivos(u):
        return _no_access()
    if request.method == "POST":
        edit_redir = _require_edit(u, "mantenimiento_preventivos")
        if edit_redir is not None:
            return edit_redir
        try:
            order = ms.create_order_from_form(request.form)
            db.session.commit()
            flash("Mantenimiento programado.", "success")
            return redirect(url_for("mantenimiento.order_detail", order_id=order.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    filtros = ms.parse_order_filtros(request.args)
    equipos, components = _components_by_equipo()
    return render_template(
        "mantenimiento/ordenes.html",
        rows=ms.list_orders(filtros),
        filtros=filtros,
        equipos=equipos,
        components=components,
        users=ms.list_users_for_responsable(),
        export_query=request.query_string.decode("utf-8"),
        **ms.labels_context(),
    )


@bp.get("/ordenes/export.xlsx")
@login_required
def ordenes_export():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_preventivos(u):
        return _no_access()
    filtros = ms.parse_order_filtros(request.args)
    data = ms.export_orders_xlsx(ms.list_orders(filtros, limit=None))
    fn = f"mantenimiento_ordenes_{date.today().isoformat()}.xlsx"
    return send_file(
        BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=fn,
    )


@bp.route("/ordenes/<int:order_id>", methods=["GET", "POST"])
@login_required
def order_detail(order_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_preventivos(u):
        return _no_access()
    order = db.session.get(MaintenanceOrder, order_id)
    if order is None:
        flash("Orden de mantenimiento no encontrada.", "danger")
        return redirect(url_for("mantenimiento.ordenes"))
    if request.method == "POST":
        edit_redir = _require_edit(u, "mantenimiento_preventivos")
        if edit_redir is not None:
            return edit_redir
        try:
            ms.update_order_from_form(order, request.form)
            db.session.commit()
            flash("Orden actualizada.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        return redirect(url_for("mantenimiento.order_detail", order_id=order_id))
    equipos, components = _components_by_equipo()
    return render_template(
        "mantenimiento/orden_detalle.html",
        order=order,
        equipos=equipos,
        components=components,
        users=ms.list_users_for_responsable(),
        **ms.labels_context(),
    )


@bp.route("/recursos", methods=["GET", "POST"])
@login_required
def recursos():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_recursos(u):
        return _no_access()
    if request.method == "POST":
        edit_redir = _require_edit(u, "mantenimiento_recursos")
        if edit_redir is not None:
            return edit_redir
        try:
            ms.create_resource_from_form(request.form)
            db.session.commit()
            flash("Recurso sugerido creado.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        return redirect(url_for("mantenimiento.recursos"))
    equipos, components = _components_by_equipo()
    return render_template(
        "mantenimiento/recursos.html",
        recursos=ms.list_resources(),
        equipos=equipos,
        components=components,
        **ms.labels_context(),
    )


@bp.route("/predictivo", methods=["GET", "POST"])
@login_required
def predictivo():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_predictivo(u):
        return _no_access()
    if request.method == "POST":
        edit_redir = _require_edit(u, "mantenimiento_predictivo")
        if edit_redir is not None:
            return edit_redir
        count = ms.refresh_predictions()
        db.session.commit()
        flash(f"Predicciones actualizadas: {count}.", "success")
        return redirect(url_for("mantenimiento.predictivo"))
    return render_template("mantenimiento/predictivo.html", rows=ms.list_predictions(), **ms.labels_context())


@bp.post("/predictivo/<int:prediction_id>/programar")
@login_required
def predictivo_programar(prediction_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_predictivo(u):
        return _no_access()
    edit_redir = _require_edit(u, "mantenimiento_predictivo")
    if edit_redir is not None:
        return edit_redir
    prediction = db.session.get(MaintenancePrediction, prediction_id)
    if prediction is None:
        flash("Sugerencia predictiva no encontrada.", "danger")
        return redirect(url_for("mantenimiento.predictivo"))
    order = ms.create_order_from_prediction(prediction, request.form.get("fecha_programada"))
    db.session.commit()
    flash("Sugerencia predictiva convertida en mantenimiento programado.", "success")
    return redirect(url_for("mantenimiento.order_detail", order_id=order.id))


@bp.route("/correctivos/<int:failure_id>", methods=["GET", "POST"])
@login_required
def failure_detail(failure_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not _can_view_correctivos(u):
        return _no_access()
    failure = db.session.get(MaintenanceFailure, failure_id)
    if failure is None:
        flash("Correctivo no encontrado.", "danger")
        return redirect(url_for("mantenimiento.correctivos"))
    if request.method == "POST":
        edit_redir = _require_edit(u, "mantenimiento_correctivos")
        if edit_redir is not None:
            return edit_redir
        try:
            ms.update_failure_from_form(failure, request.form)
            ms.save_failure_attachment(failure, request.files.get("adjunto"), u)
            db.session.commit()
            flash("Correctivo actualizado.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        return redirect(url_for("mantenimiento.failure_detail", failure_id=failure_id))
    return render_template(
        "mantenimiento/correctivo_detalle.html",
        failure=failure,
        closed_value=ms.input_datetime_value(failure.closed_at_iso),
        **ms.labels_context(),
    )


@bp.get("/adjuntos/<int:attachment_id>")
@login_required
def download_attachment(attachment_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    attachment = db.session.get(MaintenanceAttachment, attachment_id)
    if attachment is None:
        flash("Adjunto no encontrado.", "danger")
        return redirect(url_for("mantenimiento.hub"))
    path = ms.resolve_attachment_path(attachment)
    if path is None:
        flash("El archivo adjunto no está disponible en disco.", "warning")
        return redirect(request.referrer or url_for("mantenimiento.hub"))
    return send_file(path, as_attachment=True, download_name=attachment.original_filename)
