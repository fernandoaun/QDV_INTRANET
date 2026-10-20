from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import plan_accion_service as svc

bp = Blueprint("plan_accion", __name__, url_prefix="/sgi/plan-accion")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI carga y edita acciones; el admin además da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver el plan de acción.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _plan(**kw):
    return render_template(
        "plan_accion/plan.html",
        responsable=svc.responsable_seguimiento(),
        ultima_actualizacion=svc.ultima_actualizacion(),
        **kw,
        **svc.labels_context(),
    )


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    return _plan(acciones=svc.listar(), blanco=False, puede_editar=puede_editar)


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _plan(acciones=[], blanco=True, puede_editar=False)


@bp.post("/responsable")
@login_required
def responsable():
    u, puede_editar, _, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para editar el plan de acción.", "warning")
    else:
        svc.guardar_responsable(request.form.get("responsable_seguimiento", ""), u.id)
        db.session.commit()
        flash("Responsable de seguimiento guardado.", "success")
    return redirect(url_for("plan_accion.hub"))


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar acciones.", "warning")
        return redirect(url_for("plan_accion.hub"))
    if request.method == "POST":
        accion, errs = svc.crear(request.form, u.id)
        if errs or accion is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash(f"Acción N° {accion.numero} cargada.", "success")
            return redirect(url_for("plan_accion.hub"))
    return render_template("plan_accion/accion.html", accion=None, datos=request.form, editar=True, puede_editar=True,
                           es_admin=es_admin, **svc.labels_context())


@bp.route("/<int:accion_id>", methods=["GET", "POST"])
@login_required
def ver(accion_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    accion = svc.get(accion_id)
    if accion is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar el plan de acción.", "warning")
            return redirect(url_for("plan_accion.ver", accion_id=accion.id))
        errs = svc.guardar(accion, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("plan_accion.ver", accion_id=accion.id, editar=1))
        db.session.commit()
        flash(f"Acción N° {accion.numero} guardada.", "success")
        return redirect(url_for("plan_accion.ver", accion_id=accion.id))
    return render_template(
        "plan_accion/accion.html",
        accion=accion,
        datos=None,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(accion) if request.args.get("historial") == "1" else None,
        **svc.labels_context(),
    )


@bp.post("/<int:accion_id>/baja")
@login_required
def baja(accion_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    accion = svc.get(accion_id)
    if accion is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja acciones.", "warning")
        return redirect(url_for("plan_accion.ver", accion_id=accion.id))
    svc.baja(accion, u.id)
    db.session.commit()
    flash(f"Acción N° {accion.numero} dada de baja. Queda en el historial.", "success")
    return redirect(url_for("plan_accion.hub"))
