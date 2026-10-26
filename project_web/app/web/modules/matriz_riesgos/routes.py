from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import matriz_riesgos_service as svc

bp = Blueprint("matriz_riesgos", __name__, url_prefix="/sgi/matriz-riesgos")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI carga y edita las matrices; el admin además da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver la matriz de riesgos y oportunidades.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _hoja(**kw):
    kw.setdefault("historial", None)
    return render_template("matriz_riesgos/matriz.html", **kw, sectores=svc.sectores(), **svc.labels_context())


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    return render_template(
        "matriz_riesgos/listado.html", matrices=svc.listar(), puede_editar=puede_editar, **svc.labels_context()
    )


@bp.get("/valoracion")
@login_required
def valoracion():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return render_template("matriz_riesgos/valoracion.html", **svc.labels_context())


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _hoja(matriz=None, blanco=True, editar=False, puede_editar=False, es_admin=False)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar matrices de riesgos.", "warning")
        return redirect(url_for("matriz_riesgos.hub"))
    if request.method == "POST":
        matriz, errs = svc.crear(request.form, u.id)
        if errs or matriz is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash(f"Matriz de {matriz.sector} cargada.", "success")
            return redirect(url_for("matriz_riesgos.ver", matriz_id=matriz.id))
    return _hoja(matriz=None, blanco=False, editar=True, puede_editar=True, es_admin=es_admin)


@bp.route("/<int:matriz_id>", methods=["GET", "POST"])
@login_required
def ver(matriz_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    matriz = svc.get(matriz_id)
    if matriz is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar matrices de riesgos.", "warning")
            return redirect(url_for("matriz_riesgos.ver", matriz_id=matriz.id))
        errs = svc.guardar(matriz, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("matriz_riesgos.ver", matriz_id=matriz.id, editar=1))
        db.session.commit()
        flash(f"Matriz de {matriz.sector} guardada.", "success")
        return redirect(url_for("matriz_riesgos.ver", matriz_id=matriz.id))
    return _hoja(
        matriz=matriz,
        blanco=False,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(matriz) if request.args.get("historial") == "1" else None,
    )


@bp.post("/<int:matriz_id>/baja")
@login_required
def baja(matriz_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    matriz = svc.get(matriz_id)
    if matriz is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja matrices de riesgos.", "warning")
        return redirect(url_for("matriz_riesgos.ver", matriz_id=matriz.id))
    svc.baja(matriz, u.id)
    db.session.commit()
    flash(f"Matriz de {matriz.sector} dada de baja. Queda en el historial.", "success")
    return redirect(url_for("matriz_riesgos.hub"))
