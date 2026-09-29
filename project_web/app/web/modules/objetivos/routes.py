"""Programas anuales del PG-02 (Objetivos 02_01, CMASS 02_02, …) en /sgi/programas/<tipo>/…

Las entradas sin parámetros (`<tipo>_hub`, `<tipo>_en_blanco`) existen para asociarlas desde el punto 7
de los procedimientos (SGI_REGISTRO_MODULOS resuelve endpoints sin argumentos).
"""
from __future__ import annotations

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for

from app.auth_utils import (
    current_user,
    login_required,
    request_wants_json,
    user_can_access_sgi,
    user_can_edit_sgi_documentos,
)
from app.extensions import db
from app.services import objetivos_service as svc

bp = Blueprint("objetivos", __name__, url_prefix="/sgi")


def _tipo(tipo: str) -> svc.TipoPrograma:
    t = svc.tipo_o_none(tipo)
    if t is None:
        abort(404)
    return t


def _perfil():
    """(usuario, puede_seguimiento, es_admin, redirect|None). SGI edita seguimiento; el admin, todo."""
    u = current_user()
    if not user_can_access_sgi(u):
        flash("No tenés permiso para ver los programas del SGI.", "warning")
        return None, False, False, redirect(url_for("main.dashboard"))
    es_admin = bool(u.is_admin)
    return u, es_admin or user_can_edit_sgi_documentos(u), es_admin, None


def _volver(tipo: str, anio: int | None = None, ancla: str = ""):
    if anio is None:
        return redirect(url_for("objetivos.hub_tipo", tipo=tipo))
    return redirect(url_for("objetivos.programa", tipo=tipo, anio=anio) + ancla)


def _denegado(msg: str, tipo: str, anio: int | None = None):
    if request_wants_json():
        return jsonify({"ok": False, "error": msg}), 403
    flash(msg, "warning")
    return _volver(tipo, anio)


# ---------------------------------------------------------------- entradas para el punto 7 del SGI


@bp.get("/objetivos/")
@login_required
def hub():
    return redirect(url_for("objetivos.hub_tipo", tipo="objetivos"))


@bp.get("/objetivos/en-blanco")
@login_required
def en_blanco():
    return en_blanco_tipo("objetivos")


@bp.get("/objetivos/<int:anio>")
@login_required
def programa_objetivos_legacy(anio: int):
    return redirect(url_for("objetivos.programa", tipo="objetivos", anio=anio))


@bp.get("/cmass/")
@login_required
def cmass_hub():
    return redirect(url_for("objetivos.hub_tipo", tipo="cmass"))


@bp.get("/cmass/en-blanco")
@login_required
def cmass_en_blanco():
    return en_blanco_tipo("cmass")


# ---------------------------------------------------------------- vistas


@bp.get("/programas/<tipo>/")
@login_required
def hub_tipo(tipo: str):
    _tipo(tipo)
    u, _, _, redir = _perfil()
    if redir is not None:
        return redir
    return redirect(url_for("objetivos.programa", tipo=tipo, anio=svc.anio_por_defecto(tipo)))


@bp.get("/programas/<tipo>/en-blanco")
@login_required
def en_blanco_tipo(tipo: str):
    """Planilla vacía del registro: solo el encabezado controlado, como el formulario sin completar."""
    t = _tipo(tipo)
    u, _, _, redir = _perfil()
    if redir is not None:
        return redir
    anios = svc.anios_disponibles(tipo)
    ref = svc.get_programa(tipo, anios[0]) if anios else None
    return render_template(
        "objetivos/programa.html",
        blanco=True,
        anio=None,
        prog=ref,
        objetivos=[],
        grupos={},
        filas_vacias=8,
        meses_map=svc.meses_map,
        anios=[],
        anio_anterior=None,
        puede_seg=False,
        es_admin=False,
        **svc.labels_context(t),
    )


@bp.get("/programas/<tipo>/<int:anio>")
@login_required
def programa(tipo: str, anio: int):
    t = _tipo(tipo)
    u, puede_seg, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(tipo, anio)
    anios = svc.anios_disponibles(tipo)
    objs = svc.objetivos_activos(prog) if prog else []
    return render_template(
        "objetivos/programa.html",
        blanco=False,
        anio=anio,
        prog=prog,
        objetivos=objs,
        grupos=svc.grupos_por_proceso(objs) if t.agrupar_proceso else {},
        meses_map=svc.meses_map,
        anios=sorted(set(anios) | {anio, svc._today().year}, reverse=True),
        anio_anterior=next((a for a in anios if a < anio), None),
        puede_seg=puede_seg,
        es_admin=es_admin,
        **svc.labels_context(t),
    )


@bp.get("/programas/<tipo>/<int:anio>/historial")
@login_required
def historial(tipo: str, anio: int):
    t = _tipo(tipo)
    u, _, _, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(tipo, anio)
    if prog is None:
        return _volver(tipo, anio)
    return render_template(
        "objetivos/historial.html", anio=anio, prog=prog, cambios=svc.cambios_recientes(prog), **svc.labels_context(t)
    )


@bp.get("/programas/<tipo>/<int:anio>/export.xlsx")
@login_required
def exportar(tipo: str, anio: int):
    t = _tipo(tipo)
    u, _, _, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(tipo, anio)
    if prog is None:
        return _volver(tipo, anio)
    fn = f"{prog.codigo}_{t.nombre.replace(' ', '_')}_{anio}.xlsx"
    return Response(
        svc.exportar_xlsx(prog),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


# ---------------------------------------------------------------- administración del programa


@bp.post("/programas/<tipo>/<int:anio>/crear")
@login_required
def crear(tipo: str, anio: int):
    t = _tipo(tipo)
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    if not es_admin:
        return _denegado("Solo el administrador crea programas.", tipo, anio)
    if svc.get_programa(tipo, anio) is not None:
        flash(f"El {t.nombre} {anio} ya existe.", "info")
        return _volver(tipo, anio)
    origen = None
    raw = (request.form.get("copiar_de") or "").strip()
    if raw.isdigit():
        origen = svc.get_programa(tipo, int(raw))
    svc.crear_programa(tipo, anio, u.id, copiar_de=origen)
    db.session.commit()
    flash(f"{t.nombre} {anio} creado" + (f" con las filas abiertas de {origen.anio}." if origen else "."), "success")
    return _volver(tipo, anio)


@bp.post("/programas/<tipo>/<int:anio>/importar")
@login_required
def importar(tipo: str, anio: int):
    _tipo(tipo)
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    if not es_admin:
        return _denegado("Solo el administrador importa la planilla.", tipo, anio)
    f = request.files.get("archivo")
    if f is None or not f.filename:
        flash("Elegí el archivo .xlsx de la planilla.", "warning")
        return _volver(tipo, anio)
    prog, errs = svc.importar_planilla(f.stream, tipo, anio, u.id)
    if errs or prog is None:
        db.session.rollback()
        for e in errs:
            flash(e, "danger")
        return _volver(tipo, anio)
    db.session.commit()
    flash(f"Planilla importada: {len(svc.objetivos_activos(prog))} fila(s).", "success")
    return _volver(tipo, anio)


@bp.post("/programas/<tipo>/<int:anio>/encabezado")
@login_required
def encabezado(tipo: str, anio: int):
    _tipo(tipo)
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(tipo, anio)
    if not es_admin or prog is None:
        return _denegado("Solo el administrador edita el encabezado.", tipo, anio)
    errs = svc.actualizar_encabezado(prog, request.form, u.id)
    if errs:
        db.session.rollback()
        for e in errs:
            flash(e, "danger")
    else:
        db.session.commit()
        flash("Encabezado actualizado.", "success")
    return _volver(tipo, anio)


@bp.post("/programas/<tipo>/<int:anio>/filas")
@login_required
def alta(tipo: str, anio: int):
    t = _tipo(tipo)
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    prog = svc.get_programa(tipo, anio)
    if not es_admin or prog is None:
        return _denegado(f"Solo el administrador agrega {t.fila}es.", tipo, anio)
    obj, errs = svc.alta_objetivo(prog, request.form, u.id)
    if errs:
        db.session.rollback()
        for e in errs:
            flash(e, "danger")
    else:
        db.session.commit()
        flash(f"{t.fila.capitalize()} agregado{'a' if t.fila.endswith('a') else ''}.", "success")
    return _volver(tipo, anio, f"#obj-{obj.id}" if obj else "")


# ---------------------------------------------------------------- filas


def _fila_o_404(objetivo_id: int):
    obj = svc.get_objetivo(objetivo_id)
    if obj is None:
        abort(404)
    return obj, svc.TIPOS[obj.programa.tipo]


@bp.post("/programas/fila/<int:objetivo_id>/editar")
@login_required
def editar(objetivo_id: int):
    u, puede_seg, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    obj, t = _fila_o_404(objetivo_id)
    tipo, anio = obj.programa.tipo, obj.programa.anio
    if not puede_seg:
        return _denegado("No tenés permiso para editar el programa.", tipo, anio)
    campos = t.campos_seguimiento + (t.campos_admin if es_admin else ())
    errs = svc.actualizar_campos(obj, request.form, campos, u.id)
    if errs:
        db.session.rollback()
        for e in errs:
            flash(e, "danger")
    else:
        db.session.commit()
        flash("Cambios guardados.", "success")
    return _volver(tipo, anio, f"#obj-{obj.id}")


@bp.post("/programas/fila/<int:objetivo_id>/baja")
@login_required
def baja(objetivo_id: int):
    u, _, es_admin, redir = _perfil()
    if redir is not None:
        return redir
    obj, t = _fila_o_404(objetivo_id)
    tipo, anio = obj.programa.tipo, obj.programa.anio
    if not es_admin:
        return _denegado(f"Solo el administrador da de baja {t.fila}es.", tipo, anio)
    svc.baja_objetivo(obj, u.id)
    db.session.commit()
    flash("Dado de baja. Queda en el historial.", "success")
    return _volver(tipo, anio)


@bp.post("/programas/fila/<int:objetivo_id>/mes")
@login_required
def mes(objetivo_id: int):
    u, puede_seg, _, redir = _perfil()
    if redir is not None:
        return jsonify({"ok": False, "error": "Sin acceso."}), 403
    obj = svc.get_objetivo(objetivo_id)
    if obj is None or not obj.activo:
        return jsonify({"ok": False, "error": "Fila no encontrada."}), 404
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
