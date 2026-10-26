from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import evaluacion_desempeno_service as svc

bp = Blueprint("evaluacion_desempeno", __name__, url_prefix="/sgi/evaluaciones-desempeno")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI carga y edita evaluaciones; el admin además da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver las evaluaciones de desempeño.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _hoja(**kw):
    kw.setdefault("historial", None)
    kw.setdefault("empleados", svc.empleados() if kw.get("editar") else [])
    return render_template("evaluacion_desempeno/evaluacion.html", **kw, **svc.labels_context())


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    return render_template(
        "evaluacion_desempeno/listado.html", evaluaciones=svc.listar(), puede_editar=puede_editar, **svc.labels_context()
    )


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _hoja(ev=None, blanco=True, editar=False, puede_editar=False, es_admin=False)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar evaluaciones de desempeño.", "warning")
        return redirect(url_for("evaluacion_desempeno.hub"))
    if request.method == "POST":
        ev, errs = svc.crear(request.form, u.id)
        if errs or ev is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash(f"Evaluación N° {ev.numero} cargada.", "success")
            return redirect(url_for("evaluacion_desempeno.ver", evaluacion_id=ev.id))
    return _hoja(ev=None, blanco=False, editar=True, puede_editar=True, es_admin=es_admin)


@bp.route("/<int:evaluacion_id>", methods=["GET", "POST"])
@login_required
def ver(evaluacion_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    ev = svc.get(evaluacion_id)
    if ev is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar evaluaciones de desempeño.", "warning")
            return redirect(url_for("evaluacion_desempeno.ver", evaluacion_id=ev.id))
        errs = svc.guardar(ev, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("evaluacion_desempeno.ver", evaluacion_id=ev.id, editar=1))
        db.session.commit()
        flash(f"Evaluación N° {ev.numero} guardada.", "success")
        return redirect(url_for("evaluacion_desempeno.ver", evaluacion_id=ev.id))
    return _hoja(
        ev=ev,
        blanco=False,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(ev) if request.args.get("historial") == "1" else None,
    )


@bp.post("/<int:evaluacion_id>/baja")
@login_required
def baja(evaluacion_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    ev = svc.get(evaluacion_id)
    if ev is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja evaluaciones de desempeño.", "warning")
        return redirect(url_for("evaluacion_desempeno.ver", evaluacion_id=ev.id))
    svc.baja(ev, u.id)
    db.session.commit()
    flash(f"Evaluación N° {ev.numero} dada de baja. Queda en el historial.", "success")
    return redirect(url_for("evaluacion_desempeno.hub"))
