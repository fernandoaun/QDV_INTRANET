from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for

from app.auth_utils import (
    current_user,
    login_required,
    user_can_access_vencimientos,
    user_can_manage_vencimientos,
    user_display_name,
)
from app.extensions import db
from app.models import Vencimiento
from app.services.mail_service import is_mail_fully_configured
from app.services import vencimiento_service as vs
from app.utils.datetime_operacion import now_operacion_naive_local

bp = Blueprint("vencimientos", __name__, url_prefix="/vencimientos")


def _no_access():
    flash("No tenés permiso para acceder a Vencimientos.", "warning")
    return redirect(url_for("main.dashboard"))


def _no_mutate():
    flash("Solo un administrador puede realizar esta acción.", "warning")
    return redirect(request.referrer or url_for("vencimientos.listado"))


def _require_view():
    u = current_user()
    if not user_can_access_vencimientos(u):
        return None, _no_access()
    return u, None


@bp.get("/")
@login_required
def listado():
    u, redir = _require_view()
    if redir is not None:
        return redir
    args = vs.filter_args_from_request(request.args)
    rows = vs.fetch_list_sync_estados(args)
    sectores = vs.list_sectores(solo_activos=False)
    mail_ok = is_mail_fully_configured(current_app)
    show_mail_alert = bool(user_can_manage_vencimientos(u)) and not mail_ok
    dias_aviso = vs.dias_antes_aviso_mail(current_app)
    return render_template(
        "vencimientos/list.html",
        rows=rows,
        sectores=sectores,
        filtros=args,
        puede_gestionar=user_can_manage_vencimientos(u),
        estados_labels=vs.ESTADO_LABELS,
        estado_visual_row=vs.estado_visual_row,
        dias_restantes=vs.dias_restantes,
        mail_inactivo_alert=show_mail_alert,
        mail_configurado=mail_ok,
        dias_aviso_mail=dias_aviso,
    )


@bp.get("/export.xlsx")
@login_required
def export_xlsx():
    u, redir = _require_view()
    if redir is not None:
        return redir
    args = vs.filter_args_from_request(request.args)
    rows = vs.fetch_list_sync_estados(args)
    bio = vs.build_export_xlsx(rows)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return send_file(
        bio,
        as_attachment=True,
        download_name=f"vencimientos_{ts}.xlsx",
        max_age=0,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not user_can_manage_vencimientos(u):
        return _no_mutate()
    sectores = vs.list_sectores(solo_activos=True)
    if request.method == "POST":
        row, err = vs.create_vencimiento(dict(request.form), u.id, user_display_name(u))
        if err:
            flash(err, "danger")
            return render_template("vencimientos/form.html", modo="nuevo", sectores=sectores, form=request.form)
        flash("Vencimiento creado.", "success")
        f = request.files.get("archivo")
        if f and (f.filename or "").strip():
            ok_att, msg_att = vs.save_attachment(row.id, f, u.id, user_display_name(u))
            flash(msg_att, "success" if ok_att else "warning")
        return redirect(url_for("vencimientos.detalle", vid=row.id))
    return render_template("vencimientos/form.html", modo="nuevo", sectores=sectores, form=None)


@bp.route("/<int:vid>/editar", methods=["GET", "POST"])
@login_required
def editar(vid: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    v = vs.get_vencimiento(vid)
    if v is None:
        flash("Registro no encontrado.", "danger")
        return redirect(url_for("vencimientos.listado"))
    sectores = vs.list_sectores(solo_activos=False)
    if not user_can_manage_vencimientos(u):
        return _no_mutate()
    if request.method == "POST":
        ok, msg = vs.update_vencimiento(vid, dict(request.form), u.id, user_display_name(u))
        flash(msg, "success" if ok else "danger")
        if ok:
            f = request.files.get("archivo")
            if f and (f.filename or "").strip():
                ok_att, msg_att = vs.save_attachment(vid, f, u.id, user_display_name(u))
                flash(msg_att, "success" if ok_att else "warning")
            return redirect(url_for("vencimientos.detalle", vid=vid))
    form_prefill = {
        "sector_id": str(v.sector_id),
        "nombre": v.nombre,
        "descripcion": v.descripcion,
        "fecha_vencimiento": v.fecha_vencimiento.isoformat(),
        "responsable": v.responsable,
        "email_aviso": v.email_aviso,
        "observaciones": v.observaciones,
    }
    return render_template("vencimientos/form.html", modo="editar", sectores=sectores, v=v, form=form_prefill)


@bp.get("/<int:vid>")
@login_required
def detalle(vid: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    v = vs.get_vencimiento(vid)
    if v is None:
        flash("Registro no encontrado.", "danger")
        return redirect(url_for("vencimientos.listado"))
    t = now_operacion_naive_local().date()
    if vs.sync_derived_estado(v, t):
        v.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        db.session.refresh(v)
    hist = vs.historial_for(vid)
    predecesor = None
    if v.continuacion_de_id:
        predecesor = db.session.get(Vencimiento, int(v.continuacion_de_id))
    return render_template(
        "vencimientos/detail.html",
        v=v,
        hist=hist,
        predecesor=predecesor,
        puede_gestionar=user_can_manage_vencimientos(u),
        estados_labels=vs.ESTADO_LABELS,
        estado_visual_row=vs.estado_visual_row,
        dias_restantes=vs.dias_restantes,
    )


@bp.post("/<int:vid>/desactivar")
@login_required
def desactivar(vid: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not user_can_manage_vencimientos(u):
        return _no_mutate()
    ok, msg = vs.deactivate_vencimiento(vid, u.id, user_display_name(u))
    flash(msg, "success" if ok else "warning")
    return redirect(url_for("vencimientos.listado"))


@bp.post("/<int:vid>/renovar")
@login_required
def renovar(vid: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not user_can_manage_vencimientos(u):
        return _no_mutate()
    nd = vs.parse_iso_date(request.form.get("nueva_fecha_vencimiento"))
    if nd is None:
        flash("Indicá una fecha de renovación válida.", "danger")
        return redirect(url_for("vencimientos.detalle", vid=vid))
    nuevo, msg = vs.renew_vencimiento(vid, nd, u.id, user_display_name(u))
    flash(msg, "success" if nuevo else "danger")
    if nuevo:
        return redirect(url_for("vencimientos.detalle", vid=nuevo.id))
    return redirect(url_for("vencimientos.detalle", vid=vid))


@bp.post("/<int:vid>/adjunto")
@login_required
def adjunto_subir(vid: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not user_can_manage_vencimientos(u):
        return _no_mutate()
    f = request.files.get("archivo")
    ok, msg = vs.save_attachment(vid, f, u.id, user_display_name(u))
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("vencimientos.detalle", vid=vid))


@bp.get("/<int:vid>/archivo")
@login_required
def adjunto_descargar(vid: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    v = vs.get_vencimiento(vid)
    if v is None or not v.archivo_path:
        abort(404)
    path = vs.attachment_absolute_path(v.archivo_path)
    if path is None:
        abort(404)
    dl = path.name
    inline = request.args.get("inline", "").strip().lower() in ("1", "true", "yes")
    return send_file(path, as_attachment=not inline, download_name=dl if not inline else None, max_age=0)


@bp.route("/sectores", methods=["GET", "POST"])
@login_required
def sectores():
    u, redir = _require_view()
    if redir is not None:
        return redir
    if not user_can_manage_vencimientos(u):
        flash("Solo un administrador puede gestionar sectores.", "warning")
        return redirect(url_for("vencimientos.listado"))
    if request.method == "POST":
        act = (request.form.get("action") or "").strip()
        if act == "crear":
            ok, msg = vs.create_sector(request.form.get("nombre"), request.form.get("descripcion"), u.id)
            flash(msg, "success" if ok else "danger")
        elif act == "editar":
            ok, msg = vs.update_sector(
                int(request.form.get("sector_id") or 0),
                request.form.get("nombre"),
                request.form.get("descripcion"),
                request.form.get("activo") == "1",
            )
            flash(msg, "success" if ok else "danger")
        return redirect(url_for("vencimientos.sectores"))
    rows = vs.list_sectores(solo_activos=False)
    return render_template("vencimientos/sectores.html", sectores=rows)
