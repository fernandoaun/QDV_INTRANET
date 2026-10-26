from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import minuta_reunion_service as svc

bp = Blueprint("minuta_reunion", __name__, url_prefix="/sgi/minutas-reunion")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI carga y edita minutas; el admin además da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver las minutas de reunión.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _hoja(**kw):
    kw.setdefault("historial", None)
    return render_template("minuta_reunion/minuta.html", **kw, **svc.labels_context())


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    return render_template(
        "minuta_reunion/listado.html", minutas=svc.listar(), puede_editar=puede_editar, **svc.labels_context()
    )


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _hoja(minuta=None, blanco=True, editar=False, puede_editar=False, es_admin=False)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar minutas de reunión.", "warning")
        return redirect(url_for("minuta_reunion.hub"))
    if request.method == "POST":
        minuta, errs = svc.crear(request.form, u.id)
        if errs or minuta is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash(f"Minuta N° {minuta.numero} cargada.", "success")
            return redirect(url_for("minuta_reunion.ver", minuta_id=minuta.id))
    return _hoja(minuta=None, blanco=False, editar=True, puede_editar=True, es_admin=es_admin)


@bp.route("/<int:minuta_id>", methods=["GET", "POST"])
@login_required
def ver(minuta_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    minuta = svc.get(minuta_id)
    if minuta is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar minutas de reunión.", "warning")
            return redirect(url_for("minuta_reunion.ver", minuta_id=minuta.id))
        errs = svc.guardar(minuta, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("minuta_reunion.ver", minuta_id=minuta.id, editar=1))
        db.session.commit()
        flash(f"Minuta N° {minuta.numero} guardada.", "success")
        return redirect(url_for("minuta_reunion.ver", minuta_id=minuta.id))
    return _hoja(
        minuta=minuta,
        blanco=False,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(minuta) if request.args.get("historial") == "1" else None,
    )


@bp.post("/<int:minuta_id>/baja")
@login_required
def baja(minuta_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    minuta = svc.get(minuta_id)
    if minuta is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja minutas de reunión.", "warning")
        return redirect(url_for("minuta_reunion.ver", minuta_id=minuta.id))
    svc.baja(minuta, u.id)
    db.session.commit()
    flash(f"Minuta N° {minuta.numero} dada de baja. Queda en el historial.", "success")
    return redirect(url_for("minuta_reunion.hub"))
