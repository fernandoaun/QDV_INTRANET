from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import desvios_service as svc

bp = Blueprint("desvios", __name__, url_prefix="/sgi/desvios")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI carga y edita reportes; el admin además da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver los reportes de NC, PNC y OM.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _avisar_plan(creadas: int) -> None:
    if creadas:
        flash(f"{creadas} acción(es) con responsable pasaron al Plan de acción.", "info")


def _hoja(**kw):
    kw.setdefault("historial", None)
    return render_template("desvios/reporte.html", **kw, **svc.labels_context())


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    return render_template(
        "desvios/listado.html", desvios=svc.listar(), puede_editar=puede_editar, **svc.labels_context()
    )


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _hoja(dv=None, blanco=True, editar=False, puede_editar=False, es_admin=False)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar reportes de NC, PNC y OM.", "warning")
        return redirect(url_for("desvios.hub"))
    if request.method == "POST":
        dv, errs = svc.crear(request.form, u.id)
        if errs or dv is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            creadas = svc.sincronizar_plan(dv, u.id)
            db.session.commit()
            flash(f"Reporte N° {dv.numero} cargado.", "success")
            _avisar_plan(creadas)
            return redirect(url_for("desvios.ver", desvio_id=dv.id))
    return _hoja(dv=None, blanco=False, editar=True, puede_editar=True, es_admin=es_admin)


@bp.route("/<int:desvio_id>", methods=["GET", "POST"])
@login_required
def ver(desvio_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    dv = svc.get(desvio_id)
    if dv is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar reportes de NC, PNC y OM.", "warning")
            return redirect(url_for("desvios.ver", desvio_id=dv.id))
        errs = svc.guardar(dv, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("desvios.ver", desvio_id=dv.id, editar=1))
        creadas = svc.sincronizar_plan(dv, u.id)
        db.session.commit()
        flash(f"Reporte N° {dv.numero} guardado.", "success")
        _avisar_plan(creadas)
        return redirect(url_for("desvios.ver", desvio_id=dv.id))
    return _hoja(
        dv=dv,
        blanco=False,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(dv) if request.args.get("historial") == "1" else None,
    )


@bp.post("/<int:desvio_id>/baja")
@login_required
def baja(desvio_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    dv = svc.get(desvio_id)
    if dv is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja reportes.", "warning")
        return redirect(url_for("desvios.ver", desvio_id=dv.id))
    svc.baja(dv, u.id)
    db.session.commit()
    flash(f"Reporte N° {dv.numero} dado de baja. Queda en el historial.", "success")
    return redirect(url_for("desvios.hub"))


def _seguimiento(blanco: bool):
    desvios = [] if blanco else svc.listar()
    return render_template(
        "desvios/seguimiento.html",
        desvios=sorted(desvios, key=lambda d: (d.fecha or d.created_at.date(), d.numero)),
        res=svc.resumen(desvios),
        ultima_actualizacion=None if blanco else svc.ultima_actualizacion(),
        blanco=blanco,
        **svc.labels_context(),
    )


@bp.get("/seguimiento")
@login_required
def seguimiento():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _seguimiento(blanco=False)


@bp.get("/seguimiento/en-blanco")
@login_required
def seguimiento_en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _seguimiento(blanco=True)
