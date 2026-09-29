from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import fichas_proceso_service as svc

bp = Blueprint("fichas", __name__, url_prefix="/sgi/fichas-proceso")


def _perfil():
    """(usuario, puede_editar, es_admin, redirect|None). SGI edita las fichas; el admin además crea y da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver las fichas de proceso.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    return render_template(
        "fichas_proceso/listado.html", fichas=svc.listar(), puede_editar=puede_editar, es_admin=es_admin, **svc.labels_context()
    )


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _perfil()
    if redir is not None:
        return redir
    return render_template("fichas_proceso/ficha.html", ficha=None, blanco=True, editar=False, puede_editar=False, es_admin=False, **svc.labels_context())


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    if not es_admin:
        flash("Solo el administrador agrega fichas de proceso.", "warning")
        return redirect(url_for("fichas.hub"))
    if request.method == "POST":
        ficha, errs = svc.crear(request.form, u.id)
        if errs or ficha is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash("Ficha de proceso creada.", "success")
            return redirect(url_for("fichas.ver", ficha_id=ficha.id))
    return render_template("fichas_proceso/ficha.html", ficha=None, blanco=False, editar=True, puede_editar=True, es_admin=True, **svc.labels_context())


@bp.route("/<int:ficha_id>", methods=["GET", "POST"])
@login_required
def ver(ficha_id: int):
    u, puede_editar, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    ficha = svc.get(ficha_id)
    if ficha is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar fichas de proceso.", "warning")
            return redirect(url_for("fichas.ver", ficha_id=ficha.id))
        errs = svc.guardar(ficha, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("fichas.ver", ficha_id=ficha.id, editar=1))
        db.session.commit()
        flash("Ficha guardada.", "success")
        return redirect(url_for("fichas.ver", ficha_id=ficha.id))
    editar = puede_editar and request.args.get("editar") == "1"
    return render_template(
        "fichas_proceso/ficha.html",
        ficha=ficha,
        blanco=False,
        editar=editar,
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(ficha) if request.args.get("historial") == "1" else None,
        **svc.labels_context(),
    )


@bp.post("/<int:ficha_id>/baja")
@login_required
def baja(ficha_id: int):
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    ficha = svc.get(ficha_id)
    if ficha is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja fichas de proceso.", "warning")
        return redirect(url_for("fichas.ver", ficha_id=ficha.id))
    svc.baja(ficha, u.id)
    db.session.commit()
    flash(f"Ficha «{ficha.proceso}» dada de baja. Queda en el historial.", "success")
    return redirect(url_for("fichas.hub"))
