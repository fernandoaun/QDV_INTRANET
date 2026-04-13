from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for

from app.auth_utils import (
    current_user,
    login_required,
    user_can_access_planificacion,
    user_can_edit,
)
from app.extensions import db
from app.models import PlanificacionActividad
from app.services import planificacion_service as ps

bp = Blueprint("planificacion", __name__, url_prefix="/planificacion")


def _no_access():
    flash("No tenés permiso para acceder a Planificación.", "warning")
    return redirect(url_for("main.dashboard"))


def _no_edit():
    flash("No tenés permiso de edición en Planificación.", "warning")
    return redirect(request.referrer or url_for("planificacion.tabla"))


def _require_view():
    u = current_user()
    if not user_can_access_planificacion(u):
        return None, _no_access()
    return u, None


def _require_edit(u):
    if not user_can_edit(u, "planificacion"):
        return _no_edit()
    return None


def _picker_json(exclude_id: int | None) -> list[dict[str, str | int]]:
    rows = ps.list_actividades_for_pred_picker(exclude_id)
    return [{"id": r.id, "label": f"{ps.actividad_display_codigo(r)} — {r.titulo[:60]}"} for r in rows]


@bp.get("/")
@login_required
def hub():
    u, redir = _require_view()
    if redir is not None:
        return redir
    return render_template("planificacion/hub.html")


@bp.get("/tabla")
@login_required
def tabla():
    u, redir = _require_view()
    if redir is not None:
        return redir
    f = ps.parse_filtros_from_request(request.args)
    rows = ps.list_actividades(f)
    ids = [int(r.id) for r in rows]
    deps_map = ps.dependencias_entrantes_por_sucesora(ids)
    succ_map = ps.dependencias_salientes_por_predecesora(ids)
    anal_por_id: dict[int, dict[str, object]] = {}
    for r in rows:
        dlist = deps_map.get(int(r.id), [])
        anal_por_id[int(r.id)] = ps.analizar_dependencias_sucesora(r, dlist)
    return render_template(
        "planificacion/tabla.html",
        rows=rows,
        filtros=f,
        users=ps.list_users_for_responsable(),
        today=ps._today(),
        deps_map=deps_map,
        succ_map=succ_map,
        anal_por_id=anal_por_id,
        **ps.labels_context(),
    )


@bp.get("/gantt")
@login_required
def gantt():
    u, redir = _require_view()
    if redir is not None:
        return redir
    f = ps.parse_filtros_from_request(request.args)
    rows = ps.list_actividades(f)
    ids = [int(r.id) for r in rows]
    deps_map = ps.dependencias_entrantes_por_sucesora(ids)
    tasks = ps.gantt_tasks_for_rows(rows, deps_por_sucesora=deps_map)
    for t in tasks:
        t["edit_url"] = url_for("planificacion.editar", actividad_id=int(t["id"]))
    view_mode = (request.args.get("vista") or "Week").strip()
    if view_mode not in ("Quarter Day", "Half Day", "Day", "Week", "Month"):
        view_mode = "Week"
    return render_template(
        "planificacion/gantt.html",
        tasks_json=tasks,
        filtros=f,
        users=ps.list_users_for_responsable(),
        view_mode=view_mode,
        **ps.labels_context(),
    )


@bp.get("/api/tareas")
@login_required
def api_tareas():
    u, redir = _require_view()
    if redir is not None:
        return jsonify({"error": "forbidden"}), 403
    f = ps.parse_filtros_from_request(request.args)
    rows = ps.list_actividades(f)
    ids = [int(r.id) for r in rows]
    deps_map = ps.dependencias_entrantes_por_sucesora(ids)
    tasks = ps.gantt_tasks_for_rows(rows, deps_por_sucesora=deps_map)
    for t in tasks:
        t["edit_url"] = url_for("planificacion.editar", actividad_id=int(t["id"]))
    return jsonify({"tasks": tasks, "view_mode": (request.args.get("vista") or "Week").strip()})


@bp.get("/export.csv")
@login_required
def export_csv():
    u, redir = _require_view()
    if redir is not None:
        return redir
    f = ps.parse_filtros_from_request(request.args)
    rows = ps.list_actividades(f)
    data = ps.export_csv_bytes(rows)
    fn = f"planificacion_{date.today().isoformat()}.csv"
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


def _render_form_error(
    *,
    mode: str,
    row: PlanificacionActividad | None,
    form,
    default_fecha_inicio: str,
    default_fecha_fin: str,
    deps_actuales: list | None = None,
    exclude_id: int | None,
):
    deps_actuales = deps_actuales or []
    return render_template(
        "planificacion/form.html",
        mode=mode,
        row=row,
        form=form,
        users=ps.list_users_for_responsable(),
        default_fecha_inicio=default_fecha_inicio,
        default_fecha_fin=default_fecha_fin,
        deps_actuales=deps_actuales,
        picker_options_json=_picker_json(exclude_id),
        **ps.labels_context(),
    )


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, redir = _require_view()
    if redir is not None:
        return redir
    t0 = ps._today()
    t1 = t0 + timedelta(days=7)
    default_fecha_inicio = t0.isoformat()
    default_fecha_fin = t1.isoformat()
    if request.method == "POST":
        r = _require_edit(u)
        if r is not None:
            return r
        pairs, perrs = ps.parse_dependencias_form(request.form, None)
        if perrs:
            for e in perrs:
                flash(e, "danger")
            return _render_form_error(
                mode="nueva",
                row=None,
                form=request.form,
                default_fecha_inicio=default_fecha_inicio,
                default_fecha_fin=default_fecha_fin,
                deps_actuales=[],
                exclude_id=None,
            )
        stubs = ps.dependencia_stubs_for_validation(pairs)
        row, errs = ps.validate_and_build_from_form(request.form, existing=None, deps_entrantes=stubs)
        if errs or row is None:
            for e in errs:
                flash(e, "danger")
            return _render_form_error(
                mode="nueva",
                row=None,
                form=request.form,
                default_fecha_inicio=default_fecha_inicio,
                default_fecha_fin=default_fecha_fin,
                deps_actuales=[],
                exclude_id=None,
            )
        row.created_by_user_id = u.id
        db.session.add(row)
        db.session.flush()
        err_dep = ps.replace_dependencias_sucesora(int(row.id), pairs)
        if err_dep:
            db.session.rollback()
            flash(err_dep, "danger")
            return _render_form_error(
                mode="nueva",
                row=None,
                form=request.form,
                default_fecha_inicio=default_fecha_inicio,
                default_fecha_fin=default_fecha_fin,
                deps_actuales=[],
                exclude_id=None,
            )
        db.session.commit()
        flash("Actividad creada.", "success")
        return redirect(url_for("planificacion.tabla"))
    return render_template(
        "planificacion/form.html",
        mode="nueva",
        row=None,
        form=None,
        users=ps.list_users_for_responsable(),
        default_fecha_inicio=default_fecha_inicio,
        default_fecha_fin=default_fecha_fin,
        deps_actuales=[],
        picker_options_json=_picker_json(None),
        **ps.labels_context(),
    )


@bp.route("/editar/<int:actividad_id>", methods=["GET", "POST"])
@login_required
def editar(actividad_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    t0 = ps._today()
    t1 = t0 + timedelta(days=7)
    default_fecha_inicio = t0.isoformat()
    default_fecha_fin = t1.isoformat()
    row = ps.get_actividad_or_none(actividad_id)
    if row is None:
        flash("Actividad no encontrada.", "danger")
        return redirect(url_for("planificacion.tabla"))
    deps_db = ps.dependencias_entrantes_por_sucesora([int(row.id)]).get(int(row.id), [])
    if request.method == "POST":
        r = _require_edit(u)
        if r is not None:
            return r
        pairs, perrs = ps.parse_dependencias_form(request.form, int(row.id))
        if perrs:
            for e in perrs:
                flash(e, "danger")
            return _render_form_error(
                mode="editar",
                row=row,
                form=request.form,
                default_fecha_inicio=default_fecha_inicio,
                default_fecha_fin=default_fecha_fin,
                deps_actuales=deps_db,
                exclude_id=int(row.id),
            )
        stubs = ps.dependencia_stubs_for_validation(pairs)
        updated, errs = ps.validate_and_build_from_form(request.form, existing=row, deps_entrantes=stubs)
        if errs or updated is None:
            for e in errs:
                flash(e, "danger")
            return _render_form_error(
                mode="editar",
                row=row,
                form=request.form,
                default_fecha_inicio=default_fecha_inicio,
                default_fecha_fin=default_fecha_fin,
                deps_actuales=deps_db,
                exclude_id=int(row.id),
            )
        err_dep = ps.replace_dependencias_sucesora(int(row.id), pairs)
        if err_dep:
            db.session.rollback()
            db.session.refresh(row)
            flash(err_dep, "danger")
            return _render_form_error(
                mode="editar",
                row=row,
                form=request.form,
                default_fecha_inicio=default_fecha_inicio,
                default_fecha_fin=default_fecha_fin,
                deps_actuales=deps_db,
                exclude_id=int(row.id),
            )
        db.session.add(updated)
        db.session.commit()
        flash("Cambios guardados.", "success")
        return redirect(url_for("planificacion.tabla"))
    return render_template(
        "planificacion/form.html",
        mode="editar",
        row=row,
        form=None,
        users=ps.list_users_for_responsable(),
        default_fecha_inicio=default_fecha_inicio,
        default_fecha_fin=default_fecha_fin,
        deps_actuales=deps_db,
        picker_options_json=_picker_json(int(row.id)),
        **ps.labels_context(),
    )


@bp.post("/eliminar/<int:actividad_id>")
@login_required
def eliminar(actividad_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    r = _require_edit(u)
    if r is not None:
        return r
    row = ps.get_actividad_or_none(actividad_id)
    if row is None:
        flash("Actividad no encontrada.", "danger")
        return redirect(url_for("planificacion.tabla"))
    db.session.delete(row)
    db.session.commit()
    flash("Actividad eliminada.", "success")
    return redirect(url_for("planificacion.tabla"))


@bp.post("/estado/<int:actividad_id>")
@login_required
def cambiar_estado(actividad_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    r = _require_edit(u)
    if r is not None:
        return r
    row = ps.get_actividad_or_none(actividad_id)
    if row is None:
        flash("Actividad no encontrada.", "danger")
        return redirect(url_for("planificacion.tabla"))
    nuevo = (request.form.get("estado") or "").strip()
    if nuevo not in ps.ESTADOS:
        flash("Estado inválido.", "warning")
        return redirect(url_for("planificacion.tabla"))
    prev = row.estado
    deps = ps.dependencias_entrantes_por_sucesora([int(row.id)]).get(int(row.id), [])
    v = ps.validate_estado_con_dependencias(row, prev, nuevo, deps)
    if v:
        flash(v, "danger")
        return redirect(url_for("planificacion.tabla"))
    row.estado = nuevo
    db.session.add(row)
    db.session.commit()
    flash("Estado actualizado.", "success")
    return redirect(url_for("planificacion.tabla"))
