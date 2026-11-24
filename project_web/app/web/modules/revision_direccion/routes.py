from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import revision_direccion_service as svc

bp = Blueprint("revision_direccion", __name__, url_prefix="/sgi/revision-direccion")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI carga y edita; el admin además da de baja."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver las minutas de revisión por la dirección.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _avisar_plan(creadas: int) -> None:
    if creadas:
        flash(f"{creadas} acción(es) con responsable pasaron al Plan de acción.", "info")


def _pedir_firmas(rev, u) -> None:
    avisados = svc.avisar_firmas(current_app._get_current_object(), rev, excluir_user_id=u.id)
    if avisados:
        flash(f"Se pidió la firma por mail y WhatsApp a {avisados} participante(s).", "info")
    if svc.puede_firmar(rev, u):
        flash("Falta tu firma: revisá la minuta y tocá «Firmar».", "warning")


def _hoja(**kw):
    kw.setdefault("historial", None)
    r = kw.get("rev")
    kw["puede_firmar"] = bool(r) and svc.puede_firmar(r, current_user())
    kw["firmas"] = svc.firmas(r) if r else (0, 0)
    kw["nombres_usuarios"] = svc.nombres_usuarios() if kw.get("editar") else []
    return render_template("revision_direccion/revision.html", **kw, **svc.labels_context())


@bp.get("/")
@login_required
def hub():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    return render_template(
        "revision_direccion/listado.html", revisiones=svc.listar(), puede_editar=puede_editar, firmas=svc.firmas,
        **svc.labels_context()
    )


@bp.get("/en-blanco")
@login_required
def en_blanco():
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    return _hoja(rev=None, blanco=True, editar=False, puede_editar=False, es_admin=False)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def nueva():
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar minutas de revisión por la dirección.", "warning")
        return redirect(url_for("revision_direccion.hub"))
    if request.method == "POST":
        rev, errs = svc.crear(request.form, u.id)
        if errs or rev is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return _hoja(rev=None, blanco=False, editar=True, puede_editar=True, es_admin=es_admin, previo=request.form)
        creadas = svc.sincronizar_plan(rev, u.id)
        db.session.commit()
        flash(f"Minuta de revisión por la dirección N° {rev.numero} cargada.", "success")
        _avisar_plan(creadas)
        _pedir_firmas(rev, u)
        return redirect(url_for("revision_direccion.ver", revision_id=rev.id))
    return _hoja(rev=None, blanco=False, editar=True, puede_editar=True, es_admin=es_admin)


@bp.route("/<int:revision_id>", methods=["GET", "POST"])
@login_required
def ver(revision_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    rev = svc.get(revision_id)
    if rev is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar minutas de revisión por la dirección.", "warning")
            return redirect(url_for("revision_direccion.ver", revision_id=rev.id))
        errs, cambio = svc.guardar(rev, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("revision_direccion.ver", revision_id=rev.id, editar=1))
        creadas = svc.sincronizar_plan(rev, u.id)
        db.session.commit()
        flash(f"Minuta N° {rev.numero} guardada.", "success")
        _avisar_plan(creadas)
        if cambio:
            _pedir_firmas(rev, u)
        return redirect(url_for("revision_direccion.ver", revision_id=rev.id))
    return _hoja(
        rev=rev,
        blanco=False,
        editar=puede_editar and request.args.get("editar") == "1",
        puede_editar=puede_editar,
        es_admin=es_admin,
        historial=svc.cambios(rev) if request.args.get("historial") == "1" else None,
    )


@bp.post("/<int:revision_id>/firmar")
@login_required
def firmar(revision_id: int):
    u = current_user()
    rev = svc.get(revision_id)
    if rev is None:
        abort(404)
    try:
        msg = svc.firmar(rev, u, "sistema")
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "warning")
    else:
        db.session.commit()
        flash(msg, "success")
    if not user_can_access_sgi(u):
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("revision_direccion.ver", revision_id=rev.id))


@bp.post("/<int:revision_id>/baja")
@login_required
def baja(revision_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    rev = svc.get(revision_id)
    if rev is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja minutas de revisión por la dirección.", "warning")
        return redirect(url_for("revision_direccion.ver", revision_id=rev.id))
    svc.baja(rev, u.id)
    db.session.commit()
    flash(f"Minuta N° {rev.numero} dada de baja. Queda en el historial.", "success")
    return redirect(url_for("revision_direccion.hub"))
