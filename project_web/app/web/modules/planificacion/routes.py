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


def _safe_next(default_endpoint: str = "planificacion.tabla") -> str:
    """Vuelve a la pantalla de origen (almanaque o tabla) si `next` es una ruta propia del módulo."""
    nxt = (request.values.get("next") or "").strip()
    if nxt.startswith("/planificacion") and "//" not in nxt and "\\" not in nxt:
        return nxt
    return url_for(default_endpoint)


def _picker_json(exclude_id: int | None) -> list[dict[str, str | int]]:
    rows = ps.list_actividades_for_pred_picker(exclude_id)
    return [{"id": r.id, "label": f"{ps.actividad_display_codigo(r)} — {r.titulo[:60]}"} for r in rows]


def _extender_series() -> None:
    """Las tareas repetitivas sin fin se programan solas: completa las que falten antes de mostrar."""
    try:
        ps.extender_series()
    except Exception:
        db.session.rollback()


@bp.get("/")
@login_required
def hub():
    """Pantalla principal: almanaque del mes (más la primera semana del siguiente al cierre del mes)."""
    u, redir = _require_view()
    if redir is not None:
        return redir
    _extender_series()
    today = ps._today()
    mes = ps.parse_mes(request.args.get("mes"))
    desde, hasta = ps.ventana_mes(today, mes)
    f = ps.parse_filtros_from_request(request.args)
    f.estado = None
    f.fecha_desde, f.fecha_hasta = desde, hasta
    rows = ps.list_actividades(f)
    es_mes_actual = desde == today.replace(day=1)
    atrasadas = ps.list_atrasadas_antes_de(desde, f) if es_mes_actual else []
    mes_anterior = (desde - timedelta(days=1)).replace(day=1)
    mes_siguiente = (ps._ultimo_dia_mes(desde) + timedelta(days=1))
    filtros_extra = {k: v for k, v in request.args.items() if k in ("responsable_user_id", "categoria") and v}
    return render_template(
        "planificacion/almanaque.html",
        semanas=ps.almanaque_semanas(desde, hasta, rows, today),
        atrasadas=atrasadas,
        desde=desde,
        hasta=hasta,
        today=today,
        es_mes_actual=es_mes_actual,
        titulo_mes=f"{ps.MESES_LABELS[desde.month - 1]} {desde.year}",
        titulo_mes_siguiente=ps.MESES_LABELS[mes_siguiente.month - 1].lower(),
        mes_anterior=mes_anterior.strftime("%Y-%m"),
        mes_siguiente=mes_siguiente.strftime("%Y-%m"),
        filtros=f,
        filtros_extra=filtros_extra,
        dias_semana=ps.DIAS_SEMANA_CORTOS,
        users=ps.list_users_for_responsable(),
        **ps.labels_context(),
    )


@bp.get("/tabla")
@login_required
def tabla():
    u, redir = _require_view()
    if redir is not None:
        return redir
    _extender_series()
    f = ps.parse_filtros_from_request(request.args)
    today = ps._today()
    # Sin fechas en la URL se muestra el mes en curso: las tareas repetitivas llegan a un año adelante.
    ventana_default = f.fecha_desde is None and f.fecha_hasta is None
    atrasadas_previas = 0
    if ventana_default:
        f.fecha_desde, f.fecha_hasta = ps.ventana_mes(today)
        atrasadas_previas = len(ps.list_atrasadas_antes_de(f.fecha_desde, f))
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
        today=today,
        ventana_default=ventana_default,
        timedelta_1d=timedelta(days=1),
        atrasadas_previas=atrasadas_previas,
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
    _extender_series()
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
    _extender_series()
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
        serie_total=ps.contar_serie(row.serie_id) if row is not None else 0,
        serie_regla=ps.describir_serie(row.serie_id) if row is not None else "",
        volver_url=_safe_next(),
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
        rep, rep_errs = ps.parse_repeticion_form(request.form, row.fecha_inicio if row is not None else None)
        errs = list(errs) + rep_errs
        fechas: list = []
        if row is not None and rep is not None and not errs:
            fechas, ferr = ps.fechas_repeticion(row.fecha_inicio, row.fecha_fin, rep)
            if ferr:
                errs.append(ferr)
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
        copias: list = []
        if fechas:
            copias, err_rep = ps.crear_repeticiones(row, fechas, rep)
            if err_rep:
                db.session.rollback()
                flash(err_rep, "danger")
                return _render_form_error(
                    mode="nueva",
                    row=None,
                    form=request.form,
                    default_fecha_inicio=default_fecha_inicio,
                    default_fecha_fin=default_fecha_fin,
                    deps_actuales=[],
                    exclude_id=None,
                )
        db.session.flush()
        # Las predecesoras aplican solo a la primera ocurrencia de una serie.
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
        if fechas:
            ultima = copias[-1].fecha_inicio if copias else row.fecha_inicio
            flash(
                f"Tarea repetitiva creada ({ps.describir_serie(row.serie_id)}): {len(copias) + 1} fecha(s) programadas "
                f"del {row.fecha_inicio.strftime('%d/%m/%Y')} al {ultima.strftime('%d/%m/%Y')}."
                + (" Se siguen programando solas hacia adelante." if rep is not None and rep.sin_fin else ""),
                "success",
            )
        else:
            flash("Actividad creada.", "success")
        return redirect(_safe_next())
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
        volver_url=_safe_next(),
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
        return redirect(_safe_next())
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
        serie_total=ps.contar_serie(row.serie_id),
        serie_regla=ps.describir_serie(row.serie_id),
        volver_url=_safe_next(),
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
    return redirect(_safe_next())


@bp.post("/eliminar-serie/<int:actividad_id>")
@login_required
def eliminar_serie(actividad_id: int):
    """Elimina esta actividad y las siguientes de su serie; las anteriores quedan como historial."""
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
    rows = ps.serie_restantes(row)
    ps.detener_serie(row.serie_id)
    for x in rows:
        db.session.delete(x)
    db.session.commit()
    flash(f"Se eliminaron {len(rows)} actividad(es) de la serie y la repetición quedó detenida.", "success")
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
    # Desde el almanaque el cambio se hace sin recargar: responde JSON.
    quiere_json = request.headers.get("X-Requested-With") == "fetch"
    volver = _safe_next()

    def _error(msg: str, status: int = 400):
        if quiere_json:
            return jsonify({"ok": False, "error": msg}), status
        flash(msg, "danger")
        return redirect(volver)

    row = ps.get_actividad_or_none(actividad_id)
    if row is None:
        return _error("Actividad no encontrada.", 404)
    nuevo = (request.form.get("estado") or "").strip()
    if nuevo not in ps.ESTADOS:
        return _error("Estado inválido.")
    prev = row.estado
    deps = ps.dependencias_entrantes_por_sucesora([int(row.id)]).get(int(row.id), [])
    v = ps.validate_estado_con_dependencias(row, prev, nuevo, deps)
    if v:
        return _error(v)
    row.estado = nuevo
    db.session.add(row)
    db.session.commit()
    if quiere_json:
        return jsonify({"ok": True, "estado": nuevo, "estado_label": ps.ESTADO_LABELS[nuevo]})
    flash("Estado actualizado.", "success")
    return redirect(volver)
