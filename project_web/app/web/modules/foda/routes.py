from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import foda_service as svc

bp = Blueprint("foda", __name__, url_prefix="/sgi/foda")


def _acceso():
    """(usuario, puede_editar, redirect|None). SGI y el administrador editan el FODA."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver el FODA.", "warning")
        return None, False, redirect(url_for("main.dashboard"))
    return u, bool(u.is_admin) or user_can_edit_sgi_documentos(u), None


def _hoja(**kw):
    kw.setdefault("historial", None)
    return render_template("foda/foda.html", **kw, **svc.labels_context())


@bp.route("/", methods=["GET", "POST"])
@login_required
def hub():
    u, puede_editar, redir = _acceso()
    if redir is not None:
        return redir
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar el FODA.", "warning")
            return redirect(url_for("foda.hub"))
        n = svc.guardar(request.form, u.id)
        db.session.commit()
        flash("FODA guardado." if n else "No hubo cambios.", "success" if n else "info")
        return redirect(url_for("foda.hub"))
    return _hoja(
        foda=svc.get(),
        blanco=False,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        ultima_actualizacion=svc.ultima_actualizacion(),
        historial=svc.cambios() if request.args.get("historial") == "1" else None,
    )


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, redir = _acceso()
    if redir is not None:
        return redir
    return _hoja(foda=None, blanco=True, editar=False, puede_editar=False, ultima_actualizacion=None)
