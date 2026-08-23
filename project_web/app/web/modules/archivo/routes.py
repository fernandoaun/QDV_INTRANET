from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for

from app.auth_utils import (
    current_user,
    login_required,
    user_can_access_archivo,
    user_can_manage_archivo,
)
from app.services import archivo_service as avs

bp = Blueprint("archivo", __name__, url_prefix="/archivo")


def _no_access():
    flash("No tenés permiso para acceder a Procedimientos y registros.", "warning")
    return redirect(url_for("main.dashboard"))


def _no_manage():
    flash("No tenés permiso para cargar o modificar este archivo.", "warning")
    return redirect(request.referrer or url_for("archivo.hub"))


def _require_view():
    u = current_user()
    if not user_can_access_archivo(u):
        return None, _no_access()
    return u, None


def _require_manage(u):
    if not user_can_manage_archivo(u):
        return _no_manage()
    return None


@bp.get("/")
@login_required
def hub():
    u, redir = _require_view()
    if redir is not None:
        return redir
    avs.ensure_schema()
    tree = avs.hub_tree()
    return render_template(
        "archivo/hub.html",
        tree=tree,
        counts=avs.counts_hub(),
        puede_gestionar=user_can_manage_archivo(u),
    )


@bp.get("/procedimientos/<int:doc_id>")
@login_required
def procedimiento(doc_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    avs.ensure_schema()
    doc = avs.get_procedimiento(doc_id)
    if doc is None:
        abort(404)
    registros = avs.list_registros(doc)
    items = [
        {
            "row": r,
            "n_cargas": avs.count_cargas_registro(doc.id, avs.registro_clave(r.nombre)),
        }
        for r in registros
    ]
    return render_template(
        "archivo/procedimiento.html",
        doc=doc,
        items=items,
        puede_gestionar=user_can_manage_archivo(u),
    )


@bp.get("/procedimientos/<int:doc_id>/registros/<int:registro_id>")
@login_required
def registro(doc_id: int, registro_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    avs.ensure_schema()
    doc = avs.get_procedimiento(doc_id)
    if doc is None:
        abort(404)
    row = avs.get_registro(doc, registro_id)
    if row is None:
        abort(404)
    return render_template(
        "archivo/registro.html",
        doc=doc,
        registro=row,
        cargas=avs.list_cargas_registro(doc, row),
        puede_gestionar=user_can_manage_archivo(u),
    )


@bp.post("/procedimientos/<int:doc_id>/registros/<int:registro_id>/cargar")
@login_required
def registro_cargar(doc_id: int, registro_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    blocked = _require_manage(u)
    if blocked is not None:
        return blocked
    avs.ensure_schema()
    doc = avs.get_procedimiento(doc_id)
    if doc is None:
        abort(404)
    row = avs.get_registro(doc, registro_id)
    if row is None:
        abort(404)
    try:
        avs.save_carga_registro(
            doc,
            row,
            request.files.get("archivo"),
            titulo=request.form.get("titulo") or "",
            fecha_documento=request.form.get("fecha_documento") or "",
            notas=request.form.get("notas") or "",
            user=u,
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("archivo.registro", doc_id=doc.id, registro_id=row.id))
    flash("Archivo subido.", "success")
    return redirect(url_for("archivo.registro", doc_id=doc.id, registro_id=row.id))


@bp.get("/cargas/<int:carga_id>/descargar")
@login_required
def carga_descargar(carga_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    carga = avs.get_carga(carga_id)
    if carga is None:
        abort(404)
    path = avs.resolve_carga_path(carga)
    if path is None:
        flash("No se encontró el archivo en disco.", "danger")
        if carga.sgi_documento_id and carga.sgi_registro_id:
            return redirect(
                url_for("archivo.registro", doc_id=carga.sgi_documento_id, registro_id=carga.sgi_registro_id)
            )
        return redirect(url_for("archivo.hub"))
    return send_file(
        path,
        as_attachment=True,
        download_name=carga.original_filename,
        mimetype=carga.mime_type or None,
    )


@bp.post("/cargas/<int:carga_id>/eliminar")
@login_required
def carga_eliminar(carga_id: int):
    u, redir = _require_view()
    if redir is not None:
        return redir
    blocked = _require_manage(u)
    if blocked is not None:
        return blocked
    carga = avs.get_carga(carga_id)
    if carga is None:
        abort(404)
    doc_id = carga.sgi_documento_id
    registro_id = carga.sgi_registro_id
    avs.soft_delete_carga(carga)
    flash("Archivo quitado del listado.", "success")
    if doc_id and registro_id:
        return redirect(url_for("archivo.registro", doc_id=doc_id, registro_id=registro_id))
    return redirect(url_for("archivo.hub"))
