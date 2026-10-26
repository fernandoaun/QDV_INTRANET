from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import matriz_legal_service as svc

bp = Blueprint("matriz_legal", __name__, url_prefix="/sgi/matriz-legal")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI carga y edita requisitos; el admin además da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver la matriz legal.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _ambito() -> str:
    a = request.args.get("hoja", "nacion")
    return a if a in svc.AMBITOS else "nacion"


def _matriz(blanco: bool, puede_editar: bool):
    ambito = _ambito()
    fecha, usuario = (None, "") if blanco else svc.ultima_actualizacion()
    return render_template(
        "matriz_legal/matriz.html",
        ambito=ambito,
        requisitos=[] if blanco else svc.listar(ambito),
        cantidades={} if blanco else svc.contar(),
        ultima_fecha=fecha,
        ultimo_usuario=usuario,
        blanco=blanco,
        puede_editar=puede_editar and not blanco,
        **svc.labels_context(),
    )


@bp.get("/")
@login_required
def hub():
    u, puede_editar, _, redir = _acceso()
    if redir is not None:
        return redir
    return _matriz(False, puede_editar)


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _matriz(True, False)


def _ficha(**kw):
    kw.setdefault("historial", None)
    return render_template("matriz_legal/requisito.html", procesos=svc.procesos(), **kw, **svc.labels_context())


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar requisitos.", "warning")
        return redirect(url_for("matriz_legal.hub"))
    if request.method == "POST":
        r, errs = svc.crear(request.form, u.id)
        if errs or r is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash("Requisito cargado.", "success")
            return redirect(url_for("matriz_legal.hub", hoja=r.ambito))
    return _ficha(req=None, datos=request.form or {"ambito": _ambito()}, editar=True, puede_editar=True, es_admin=es_admin)


@bp.route("/<int:requisito_id>", methods=["GET", "POST"])
@login_required
def ver(requisito_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    r = svc.get(requisito_id)
    if r is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar la matriz legal.", "warning")
            return redirect(url_for("matriz_legal.ver", requisito_id=r.id))
        errs = svc.guardar(r, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("matriz_legal.ver", requisito_id=r.id, editar=1))
        db.session.commit()
        flash("Requisito guardado.", "success")
        return redirect(url_for("matriz_legal.hub", hoja=r.ambito))
    return _ficha(
        req=r,
        datos=None,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(r) if request.args.get("historial") == "1" else None,
    )


@bp.post("/<int:requisito_id>/baja")
@login_required
def baja(requisito_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    r = svc.get(requisito_id)
    if r is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja requisitos.", "warning")
        return redirect(url_for("matriz_legal.ver", requisito_id=r.id))
    svc.baja(r, u.id)
    db.session.commit()
    flash("Requisito dado de baja. Queda en el historial.", "success")
    return redirect(url_for("matriz_legal.hub", hoja=r.ambito))
