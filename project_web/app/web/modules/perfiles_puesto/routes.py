from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import perfiles_puesto_service as svc

bp = Blueprint("perfiles_puesto", __name__, url_prefix="/sgi/perfiles-puesto")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI edita los perfiles; el admin además crea y da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver los perfiles de puesto.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    return render_template(
        "perfiles_puesto/listado.html", perfiles=svc.listar(), puede_editar=puede_editar, es_admin=es_admin, **svc.labels_context()
    )


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return render_template("perfiles_puesto/perfil.html", perfil=None, blanco=True, editar=False, puede_editar=False, es_admin=False, **svc.labels_context())


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not es_admin:
        flash("Solo el administrador agrega perfiles de puesto.", "warning")
        return redirect(url_for("perfiles_puesto.hub"))
    if request.method == "POST":
        perfil, errs = svc.crear(request.form, u.id)
        if errs or perfil is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash("Perfil de puesto creado.", "success")
            return redirect(url_for("perfiles_puesto.ver", perfil_id=perfil.id))
    return render_template("perfiles_puesto/perfil.html", perfil=None, blanco=False, editar=True, puede_editar=True, es_admin=True, **svc.labels_context())


@bp.route("/<int:perfil_id>", methods=["GET", "POST"])
@login_required
def ver(perfil_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    perfil = svc.get(perfil_id)
    if perfil is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar perfiles de puesto.", "warning")
            return redirect(url_for("perfiles_puesto.ver", perfil_id=perfil.id))
        errs = svc.guardar(perfil, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("perfiles_puesto.ver", perfil_id=perfil.id, editar=1))
        db.session.commit()
        flash("Perfil guardado.", "success")
        return redirect(url_for("perfiles_puesto.ver", perfil_id=perfil.id))
    editar = puede_editar and request.args.get("editar") == "1"
    return render_template(
        "perfiles_puesto/perfil.html",
        perfil=perfil,
        blanco=False,
        editar=editar,
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(perfil) if request.args.get("historial") == "1" else None,
        **svc.labels_context(),
    )


@bp.post("/<int:perfil_id>/baja")
@login_required
def baja(perfil_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    perfil = svc.get(perfil_id)
    if perfil is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja perfiles de puesto.", "warning")
        return redirect(url_for("perfiles_puesto.ver", perfil_id=perfil.id))
    svc.baja(perfil, u.id)
    db.session.commit()
    flash(f"Perfil «{perfil.puesto}» dado de baja. Queda en el historial.", "success")
    return redirect(url_for("perfiles_puesto.hub"))
