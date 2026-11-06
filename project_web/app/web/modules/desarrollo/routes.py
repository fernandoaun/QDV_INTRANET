from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi, user_can_edit_sgi_documentos
from app.extensions import db
from app.services import desarrollo_service as svc

bp = Blueprint("desarrollo", __name__, url_prefix="/sgi/desarrollos")


def _acceso():
    """(usuario, puede_editar, es_admin, redirect|None). SGI y la Responsable de Control de Calidad ven y cargan."""
    from app.user_roles import user_is_responsable_laboratorio

    u = current_user()
    lab = u is not None and user_is_responsable_laboratorio(u)
    if not (user_can_access_sgi(u) or lab):
        flash("No tenés permiso para ver los desarrollos.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or lab or user_can_edit_sgi_documentos(u), es_admin, None


def _ctx(**kw):
    return {**kw, **svc.labels_context()}


@bp.get("/")
@login_required
def hub():
    u, puede_editar, _, redir = _acceso()
    if redir is not None:
        return redir
    return render_template("desarrollo/listado.html", **_ctx(desarrollos=svc.listar(), cambios=svc.cambios(), puede_editar=puede_editar))


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    u, puede_editar, _, redir = _acceso()
    if redir is not None:
        return redir
    if not puede_editar:
        flash("No tenés permiso para cargar desarrollos.", "warning")
        return redirect(url_for("desarrollo.hub"))
    if request.method == "POST":
        d, errs = svc.crear(request.form, u.id)
        if errs or d is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash(f"Desarrollo N° {d.numero} cargado. Completá la planificación y las entradas.", "success")
            return redirect(url_for("desarrollo.ver", desarrollo_id=d.id, editar=1))
    return render_template("desarrollo/nuevo.html", **_ctx())


@bp.route("/<int:desarrollo_id>", methods=["GET", "POST"])
@login_required
def ver(desarrollo_id: int):
    u, puede_editar, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    d = svc.get(desarrollo_id)
    if d is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar desarrollos.", "warning")
            return redirect(url_for("desarrollo.ver", desarrollo_id=d.id))
        errs, cambio = svc.guardar(d, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return redirect(url_for("desarrollo.ver", desarrollo_id=d.id, editar=1))
        db.session.commit()
        flash(f"Desarrollo N° {d.numero} guardado." + (" Si tenía firmas, se anularon: hay que volver a firmar." if cambio else ""), "success")
        return redirect(url_for("desarrollo.ver", desarrollo_id=d.id))
    editar = puede_editar and request.args.get("editar") == "1"
    return render_template(
        "desarrollo/desarrollo.html",
        **_ctx(d=d, h=svc.datos(d), ev=svc.evidencia(d), editar=editar, puede_editar=puede_editar, es_admin=es_admin,
               faltan=svc.faltantes(d), cambios_d=svc.cambios(d),
               firmables=[r for r in svc.FIRMANTES if svc.puede_firmar(d, u, r)],
               historial=svc.historial(d) if request.args.get("historial") == "1" else None),
    )


@bp.post("/<int:desarrollo_id>/firmar/<rol>")
@login_required
def firmar(desarrollo_id: int, rol: str):
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    d = svc.get(desarrollo_id)
    if d is None:
        abort(404)
    try:
        msg = svc.firmar(d, u, rol)
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "warning")
    else:
        db.session.commit()
        flash(msg, "success")
    return redirect(url_for("desarrollo.ver", desarrollo_id=d.id))


@bp.post("/<int:desarrollo_id>/baja")
@login_required
def baja(desarrollo_id: int):
    u, _, es_admin, redir = _acceso()
    if redir is not None:
        return redir
    d = svc.get(desarrollo_id)
    if d is None:
        abort(404)
    if not es_admin:
        flash("Solo el administrador da de baja desarrollos.", "warning")
        return redirect(url_for("desarrollo.ver", desarrollo_id=d.id))
    svc.baja(d, u.id)
    db.session.commit()
    flash(f"Desarrollo N° {d.numero} dado de baja. Queda en el historial.", "success")
    return redirect(url_for("desarrollo.hub"))


@bp.route("/<int:desarrollo_id>/cambios/nuevo", methods=["GET", "POST"])
@login_required
def cambio_nuevo(desarrollo_id: int):
    u, puede_editar, _, redir = _acceso()
    if redir is not None:
        return redir
    d = svc.get(desarrollo_id)
    if d is None:
        abort(404)
    if not puede_editar:
        flash("No tenés permiso para cargar cambios.", "warning")
        return redirect(url_for("desarrollo.ver", desarrollo_id=d.id))
    if request.method == "POST":
        c, errs = svc.crear_cambio(d, request.form, u.id)
        if errs or c is None:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
        else:
            db.session.commit()
            flash(f"Cambio N° {c.numero} cargado. Falta la firma del Responsable de Planta y de Control de Calidad.", "success")
            return redirect(url_for("desarrollo.cambio_ver", cambio_id=c.id))
    return render_template("desarrollo/cambio.html", **_ctx(d=d, c=None, h={}, editar=True, firmables=[]))


@bp.route("/cambios/<int:cambio_id>", methods=["GET", "POST"])
@login_required
def cambio_ver(cambio_id: int):
    u, puede_editar, _, redir = _acceso()
    if redir is not None:
        return redir
    c = svc.get_cambio(cambio_id)
    if c is None:
        abort(404)
    if request.method == "POST":
        if not puede_editar:
            flash("No tenés permiso para editar cambios.", "warning")
            return redirect(url_for("desarrollo.cambio_ver", cambio_id=c.id))
        errs = svc.guardar_cambio(c, request.form, u.id)
        if errs:
            db.session.rollback()
            for e in errs:
                flash(e, "danger")
            return render_template("desarrollo/cambio.html", **_ctx(d=c.desarrollo, c=c, h=svc.datos(c), editar=True, firmables=[]))
        db.session.commit()
        flash(f"Cambio N° {c.numero} guardado.", "success")
        return redirect(url_for("desarrollo.cambio_ver", cambio_id=c.id))
    editar = puede_editar and request.args.get("editar") == "1"
    return render_template(
        "desarrollo/cambio.html",
        **_ctx(d=c.desarrollo, c=c, h=svc.datos(c), editar=editar, puede_editar=puede_editar,
               firmables=[r for r in svc.FIRMANTES_CAMBIO if svc.puede_firmar_cambio(c, u, r)]),
    )


@bp.post("/cambios/<int:cambio_id>/firmar/<rol>")
@login_required
def cambio_firmar(cambio_id: int, rol: str):
    u, _, _, redir = _acceso()
    if redir is not None:
        return redir
    c = svc.get_cambio(cambio_id)
    if c is None:
        abort(404)
    try:
        msg = svc.firmar_cambio(c, u, rol)
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "warning")
    else:
        db.session.commit()
        flash(msg, "success")
    return redirect(url_for("desarrollo.cambio_ver", cambio_id=c.id))
