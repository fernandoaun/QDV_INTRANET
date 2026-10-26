from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import solicitud_cambio_service as svc

bp = Blueprint("solicitud_cambio", __name__, url_prefix="/sgi/solicitudes-cambio")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI carga y edita solicitudes; el admin además da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver las solicitudes de cambio.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _hoja(**kw):
    kw.setdefault("historial", None)
    return render_template("solicitud_cambio/solicitud.html", **kw, **svc.labels_context())


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    return render_template(
        "solicitud_cambio/listado.html", solicitudes=svc.listar(), puede_editar=puede_editar, **svc.labels_context()
    )


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _hoja(sol=None, blanco=True, editar=False, puede_editar=False, es_admin=False)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar solicitudes de cambio.", "warning")
        return redirect(url_for("solicitud_cambio.hub"))
    if request.method == "POST":
        sol, errs = svc.crear(request.form, u.id)
        if errs or sol is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash(f"Solicitud de cambio N° {sol.numero} cargada.", "success")
            return redirect(url_for("solicitud_cambio.ver", solicitud_id=sol.id))
    return _hoja(sol=None, blanco=False, editar=True, puede_editar=True, es_admin=es_admin)


@bp.route("/<int:solicitud_id>", methods=["GET", "POST"])
@login_required
def ver(solicitud_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    sol = svc.get(solicitud_id)
    if sol is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar solicitudes de cambio.", "warning")
            return redirect(url_for("solicitud_cambio.ver", solicitud_id=sol.id))
        errs = svc.guardar(sol, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("solicitud_cambio.ver", solicitud_id=sol.id, editar=1))
        db.session.commit()
        flash(f"Solicitud de cambio N° {sol.numero} guardada.", "success")
        return redirect(url_for("solicitud_cambio.ver", solicitud_id=sol.id))
    return _hoja(
        sol=sol,
        blanco=False,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(sol) if request.args.get("historial") == "1" else None,
    )


@bp.post("/<int:solicitud_id>/baja")
@login_required
def baja(solicitud_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    sol = svc.get(solicitud_id)
    if sol is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja solicitudes de cambio.", "warning")
        return redirect(url_for("solicitud_cambio.ver", solicitud_id=sol.id))
    svc.baja(sol, u.id)
    db.session.commit()
    flash(f"Solicitud de cambio N° {sol.numero} dada de baja. Queda en el historial.", "success")
    return redirect(url_for("solicitud_cambio.hub"))
