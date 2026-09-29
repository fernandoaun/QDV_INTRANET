from __future__ import annotations

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for

from app.auth_utils import (
    current_user,
    login_required,
    request_wants_json,
    user_can_access_sgi,
    user_can_edit_sgi_documentos,
)
from app.extensions import db
from app.services import objetivos_service as svc

bp = Blueprint("objetivos", __name__, url_prefix="/sgi/objetivos")


def _perfil():
    """(usuario, puede_seguimiento, es_admin) o redirect si no ve SGI."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver el Programa de Objetivos.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _denegado(msg: str, anio: int | None = None):
    if request_wants_json():
        return jsonify({"ok": False, "error": msg}), 403
    flash(msg, "warning")
    return redirect(url_for("objetivos.programa", anio=anio) if anio else url_for("objetivos.hub"))


@bp.get("/")
@login_required
def hub():
    u, _, _, redir = _perfil()
    if redir is not None:
        return redir
    return redirect(url_for("objetivos.programa", anio=svc.anio_por_defecto()))


@bp.get("/<int:anio>")
@login_required
def programa(anio: int):
    u, puede_seg, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(anio)
    anios = svc.anios_disponibles()
    return render_template(
        "objetivos/programa.html",
        anio=anio,
        prog=prog,
        objetivos=svc.objetivos_activos(prog) if prog else [],
        meses_map=svc.meses_map,
        anios=sorted(set(anios) | {anio, svc._today().year}, reverse=True),
        anio_anterior=next((a for a in anios if a < anio), None),
        puede_seg=puede_seg,
        es_admin=es_admin,
        **svc.labels_context(),
    )


@bp.get("/<int:anio>/historial")
@login_required
def historial(anio: int):
    u, _, _, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(anio)
    if prog is None:
        return redirect(url_for("objetivos.programa", anio=anio))
    return render_template(
        "objetivos/historial.html", anio=anio, prog=prog, cambios=svc.cambios_recientes(prog), **svc.labels_context()
    )


@bp.get("/<int:anio>/export.xlsx")
@login_required
def exportar(anio: int):
    u, _, _, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(anio)
    if prog is None:
        return redirect(url_for("objetivos.programa", anio=anio))
    fn = f"{prog.codigo}_Programa_de_Objetivos_{anio}.xlsx"
    return Response(
        svc.exportar_xlsx(prog),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@bp.post("/<int:anio>/crear")
@login_required
def crear(anio: int):
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    if not es_admin:
        return _denegado("Solo el administrador crea programas.", anio)
    if svc.get_programa(anio) is not None:
        flash(f"El programa {anio} ya existe.", "info")
        return redirect(url_for("objetivos.programa", anio=anio))
    origen = None
    raw = (request.form.get("copiar_de") or "").strip()
    if raw.isdigit():
        origen = svc.get_programa(int(raw))
    svc.crear_programa(anio, u.id, copiar_de=origen)
    db.session.commit()
    flash(f"Programa {anio} creado" + (f" con los objetivos abiertos de {origen.anio}." if origen else "."), "success")
    return redirect(url_for("objetivos.programa", anio=anio))


@bp.post("/<int:anio>/importar")
@login_required
def importar(anio: int):
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    if not es_admin:
        return _denegado("Solo el administrador importa la planilla.", anio)
    f = request.files.get("archivo")
    if f is None or not f.filename:
        flash("Elegí el archivo .xlsx de la planilla.", "warning")
        return redirect(url_for("objetivos.programa", anio=anio))
    prog, errs = svc.importar_planilla(f.stream, anio, u.id)
    if errs or prog is None:
        db.session.rollback()
        for e in errs:
            flash(e, "danger")
        return redirect(url_for("objetivos.programa", anio=anio))
    db.session.commit()
    flash(f"Planilla importada: {len(svc.objetivos_activos(prog))} objetivo(s).", "success")
    return redirect(url_for("objetivos.programa", anio=anio))


@bp.post("/<int:anio>/encabezado")
@login_required
def encabezado(anio: int):
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(anio)
    if not es_admin or prog is None:
        return _denegado("Solo el administrador edita el encabezado.", anio)
    errs = svc.actualizar_encabezado(prog, request.form, u.id)
    if errs:
        db.session.rollback()
        for e in errs:
            flash(e, "danger")
    else:
        db.session.commit()
        flash("Encabezado actualizado.", "success")
    return redirect(url_for("objetivos.programa", anio=anio))


@bp.post("/<int:anio>/objetivos")
@login_required
def alta(anio: int):
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(anio)
    if not es_admin or prog is None:
        return _denegado("Solo el administrador agrega objetivos.", anio)
    obj, errs = svc.alta_objetivo(prog, request.form, u.id)
    if errs:
        db.session.rollback()
        for e in errs:
            flash(e, "danger")
    else:
        db.session.commit()
        flash("Objetivo agregado.", "success")
    return redirect(url_for("objetivos.programa", anio=anio) + (f"#obj-{obj.id}" if obj else ""))


@bp.post("/objetivo/<int:objetivo_id>/editar")
@login_required
def editar(objetivo_id: int):
    u, puede_seg, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    obj = svc.get_objetivo(objetivo_id)
    if obj is None:
        flash("Objetivo no encontrado.", "danger")
        return redirect(url_for("objetivos.hub"))
    anio = obj.programa.anio
    if not puede_seg:
        return _denegado("No tenés permiso para editar el programa.", anio)
    # SGI edita tareas y estado; el administrador además la definición del objetivo.
    campos = svc.CAMPOS_SEGUIMIENTO + (svc.CAMPOS_ADMIN if es_admin else ())
    errs = svc.actualizar_campos(obj, request.form, campos, u.id)
    if errs:
        db.session.rollback()
        for e in errs:
            flash(e, "danger")
    else:
        db.session.commit()
        flash("Cambios guardados.", "success")
    return redirect(url_for("objetivos.programa", anio=anio) + f"#obj-{obj.id}")


@bp.post("/objetivo/<int:objetivo_id>/baja")
@login_required
def baja(objetivo_id: int):
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    obj = svc.get_objetivo(objetivo_id)
    if obj is None:
        return redirect(url_for("objetivos.hub"))
    if not es_admin:
        return _denegado("Solo el administrador da de baja objetivos.", obj.programa.anio)
    svc.baja_objetivo(obj, u.id)
    db.session.commit()
    flash("Objetivo dado de baja. Queda en el historial.", "success")
    return redirect(url_for("objetivos.programa", anio=obj.programa.anio))


@bp.post("/objetivo/<int:objetivo_id>/mes")
@login_required
def mes(objetivo_id: int):
    u, puede_seg, _, redir = _perfil()
    if redir is not None:
        return jsonify({"ok": False, "error": "Sin acceso."}), 403
    obj = svc.get_objetivo(objetivo_id)
    if obj is None or not obj.activo:
        return jsonify({"ok": False, "error": "Objetivo no encontrado."}), 404
    if not puede_seg:
        return jsonify({"ok": False, "error": "No tenés permiso para cambiar el seguimiento."}), 403
    data = request.get_json(silent=True) or request.form
    raw_mes = str(data.get("mes") or "")
    if not raw_mes.isdigit():
        return jsonify({"ok": False, "error": "Mes inválido."}), 400
    m, err = svc.set_mes(obj, int(raw_mes), data.get("estado"), data.get("valor"), u.id)
    if err or m is None:
        db.session.rollback()
        return jsonify({"ok": False, "error": err}), 400
    db.session.commit()
    prog = obj.programa
    return jsonify(
        {
            "ok": True,
            "mes": m.mes,
            "estado": m.estado or "",
            "valor": m.valor or "",
            "fecha_actualizacion": prog.fecha_actualizacion.strftime("%d/%m/%Y") if prog.fecha_actualizacion else "",
        }
    )
