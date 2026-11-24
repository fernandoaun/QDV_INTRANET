from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import capacitacion_service as svc

bp = Blueprint("capacitacion", __name__, url_prefix="/sgi/capacitaciones")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI carga y edita capacitaciones; el admin además da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver los registros de capacitación.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _pedir_firmas(cap, u) -> None:
    """Avisa a los asistentes y al disertante que faltan firmar; quien la cargó firma desde la hoja."""
    avisados = svc.avisar_firmas(current_app._get_current_object(), cap, excluir_user_id=u.id)
    if avisados:
        flash(f"Se pidió la firma por mail y WhatsApp a {avisados} persona(s).", "info")
    if svc.puede_firmar(cap, u):
        flash("Falta tu firma: revisá el registro y tocá «Firmar».", "warning")


def _hoja(**kw):
    kw.setdefault("historial", None)
    kw.setdefault("empleados", svc.empleados() if kw.get("editar") else [])
    cap = kw.get("cap")
    kw["puede_firmar"] = bool(cap) and svc.puede_firmar(cap, current_user())
    return render_template("capacitacion/capacitacion.html", **kw, **svc.labels_context())


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    return render_template(
        "capacitacion/listado.html", capacitaciones=svc.listar(), puede_editar=puede_editar, **svc.labels_context()
    )


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _hoja(cap=None, blanco=True, editar=False, puede_editar=False, es_admin=False)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar registros de capacitación.", "warning")
        return redirect(url_for("capacitacion.hub"))
    if request.method == "POST":
        cap, errs = svc.crear(request.form, u.id)
        if errs or cap is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash(f"Capacitación N° {cap.numero} cargada.", "success")
            _pedir_firmas(cap, u)
            return redirect(url_for("capacitacion.ver", capacitacion_id=cap.id))
    return _hoja(cap=None, blanco=False, editar=True, puede_editar=True, es_admin=es_admin)


@bp.route("/<int:capacitacion_id>", methods=["GET", "POST"])
@login_required
def ver(capacitacion_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    cap = svc.get(capacitacion_id)
    if cap is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar registros de capacitación.", "warning")
            return redirect(url_for("capacitacion.ver", capacitacion_id=cap.id))
        antes = svc.firmas(cap)
        errs = svc.guardar(cap, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("capacitacion.ver", capacitacion_id=cap.id, editar=1))
        db.session.commit()
        flash(f"Capacitación N° {cap.numero} guardada.", "success")
        if svc.firmas(cap) != antes:
            _pedir_firmas(cap, u)
        return redirect(url_for("capacitacion.ver", capacitacion_id=cap.id))
    return _hoja(
        cap=cap,
        blanco=False,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(cap) if request.args.get("historial") == "1" else None,
    )


@bp.post("/<int:capacitacion_id>/baja")
@login_required
def baja(capacitacion_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    cap = svc.get(capacitacion_id)
    if cap is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja registros de capacitación.", "warning")
        return redirect(url_for("capacitacion.ver", capacitacion_id=cap.id))
    svc.baja(cap, u.id)
    db.session.commit()
    flash(f"Capacitación N° {cap.numero} dada de baja. Queda en el historial.", "success")
    return redirect(url_for("capacitacion.hub"))


@bp.post("/<int:capacitacion_id>/firmar")
@login_required
def firmar(capacitacion_id: int):
    """Firma del asistente o del disertante con su usuario (no hace falta acceso al SGI: firma lo suyo)."""
    u = current_user()
    cap = svc.get(capacitacion_id)
    if cap is None:
        abort(404)
    try:
        msg = svc.firmar(cap, u, "sistema")
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "warning")
    else:
        db.session.commit()
        flash(msg, "success")
    if not user_can_access_sgi(u):
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("capacitacion.ver", capacitacion_id=cap.id))


@bp.post("/<int:capacitacion_id>/pedir-firmas")
@login_required
def pedir_firmas(capacitacion_id: int):
    u, puede_editar, _, redir = _acceso()
    if redir is not None:
        return redir
    cap = svc.get(capacitacion_id)
    if cap is None:
        abort(404)
    if not puede_editar:
        flash("No tenés permiso para pedir firmas.", "warning")
    else:
        avisados = svc.avisar_firmas(current_app._get_current_object(), cap, excluir_user_id=u.id)
        flash(f"Se pidió la firma a {avisados} persona(s)." if avisados else "No hay firmas para pedir (o falta el correo).",
              "info" if avisados else "warning")
    return redirect(url_for("capacitacion.ver", capacitacion_id=cap.id))
