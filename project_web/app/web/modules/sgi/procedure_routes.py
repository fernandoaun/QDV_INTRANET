"""Rutas del generador visual de procedimientos (PG / PO)."""
from __future__ import annotations

import json

from pathlib import Path

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for

from app.auth_utils import (
    current_user,
    login_required,
    user_can_access_sgi,
    user_can_edit_sgi_documentos,
    user_can_view_sgi_obsoletos,
    user_display_name,
)
from app.models.sgi import ESTADO_LABELS, PROCEDIMIENTO_SECCIONES, TIPO_CARATULA_LABELS, TIPO_LABELS
from app.models.sgi import (
    ANEXO_TIPO_ARCHIVO,
    ANEXO_TIPO_DOCUMENTO,
    ANEXO_TIPO_ORGANIGRAMA,
    ESTADO_EN_REVISION,
    SgiDocumento,
    SgiProcedimientoRevision,
    TIPO_MSGI,
)
from app.services import sgi_anexo_service as anexo_svc
from app.services import sgi_documento_perfil_service as perfil_svc
from app.services import sgi_procedimiento_service as proc_svc
from app.services import sgi_service as doc_svc
from app.web.modules.sgi.routes import _no_access, _no_mutate, _require_view, _resolve_tipo, bp


def _require_procedure_read(doc: SgiDocumento | None = None):
    """Acceso al módulo SGI o lectura de un procedimiento aprobado asignado al perfil del usuario."""
    u = current_user()
    if u is None:
        return None, _no_access()
    if user_can_access_sgi(u):
        return u, None
    if doc is not None and proc_svc.documento_accesible_por_perfil(u, doc):
        return u, None
    return None, _no_access()


def _require_procedure_workflow(rev: SgiProcedimientoRevision | None = None):
    """Acceso al editor/flujo: módulo SGI o participante asignado por nombre/correo en la carátula."""
    u = current_user()
    if u is None:
        return None, _no_access()
    if user_can_access_sgi(u):
        return u, None
    if rev is not None and proc_svc.user_participates_workflow(u, rev):
        return u, None
    return None, _no_access()


def _custom_logo_url() -> str | None:
    """Si existe img/qdv-logo.png (o jpg), usarlo en lugar del SVG embebido."""
    static_root = Path(current_app.static_folder or "")
    for name in ("qdv-logo.png", "qdv-logo.jpg", "qdv-logo.jpeg", "qdv-logo.webp"):
        if (static_root / "img" / name).is_file():
            return url_for("static", filename=f"img/{name}")
    return None


def _procedure_render_kwargs(**extra: object) -> dict:
    out: dict = {"custom_logo_url": _custom_logo_url(), **extra}
    doc = extra.get("doc")
    if isinstance(doc, SgiDocumento):
        out["firma_gerente_url"] = proc_svc.firma_gerente_url_for_document(doc)
    rev = extra.get("rev")
    if isinstance(rev, SgiProcedimientoRevision):
        out["doc_aprobado"] = rev.estado in ("aprobado", "vigente")
    return out


def _special_doc_editor_context(
    slug: str,
    doc: SgiDocumento,
    rev: SgiProcedimientoRevision,
    u,
    puede_editar: bool,
) -> dict:
    puede_marcar_revisado = proc_svc.user_can_marcar_revisado(u, rev)
    puede_aprobar = proc_svc.user_can_aprobar_revision(u, rev)
    puede_reenviar_aviso = proc_svc.user_can_reenviar_aviso(u, rev)
    solo_lectura = not puede_editar or rev.estado not in ("borrador", "en_revision")
    if rev.estado in ("en_revision", "revisado") and (puede_marcar_revisado or puede_aprobar):
        solo_lectura = True
    return {
        "slug": slug,
        "doc": doc,
        "rev": rev,
        "estados_labels": ESTADO_LABELS,
        "solo_lectura": solo_lectura,
        "puede_editar": puede_editar,
        "puede_marcar_revisado": puede_marcar_revisado,
        "puede_aprobar": puede_aprobar,
        "puede_reenviar_aviso": puede_reenviar_aviso,
        "correo_aviso_editable": puede_reenviar_aviso,
        "perfiles_aplica": perfil_svc.perfiles_aplica_documento(doc.id),
        "perfiles_opciones": perfil_svc.SGI_PERFILES_APLICABLES_LABELS,
        "firma_gerente_url": proc_svc.firma_gerente_url_for_document(doc),
    }


def _require_edit():
    u = current_user()
    if not user_can_edit_sgi_documentos(u):
        return None, _no_mutate()
    return u, None


@bp.get("/<slug>/procedimientos/")
@login_required
def listado_procedimientos(slug: str):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    if not proc_svc.tipo_soporta_visual(tipo):
        return redirect(url_for("sgi.listado", slug=slug))

    args = doc_svc.filter_args_from_request(request.args, tipo_fijo=tipo)
    rows = proc_svc.fetch_list_visual(args, tipo=tipo or "")
    proc_svc.ensure_list_visual_nombres_mayusculas(rows)
    puede_editar = user_can_edit_sgi_documentos(u)
    if not puede_editar:
        rows = [r for r in rows if proc_svc.puede_ver_documento(r, puede_editar=False, user=u)]

    row_meta: dict[int, dict] = {}
    for r in rows:
        rev = proc_svc.revision_vigente_aprobada(r) or proc_svc.revision_en_trabajo(r) or proc_svc.revision_actual(r)
        row_meta[r.id] = {
            "rev_id": rev.id if rev else None,
            "tiene_archivo": bool(r.archivo_path),
            "archivo_nombre": proc_svc.anexo_archivo_nombre(r.archivo_path),
            "puede_eliminar": proc_svc.puede_eliminar_procedimiento(r),
        }

    return render_template(
        "sgi/procedure_list.html",
        slug=slug,
        tipo=tipo,
        tipo_label=TIPO_LABELS.get(tipo or "", tipo or ""),
        rows=rows,
        row_meta=row_meta,
        filtros=args,
        estados_labels=ESTADO_LABELS,
        estado_visual_row=proc_svc.estado_visual_row,
        puede_editar=puede_editar,
        puede_obsoletos=user_can_view_sgi_obsoletos(u),
    )


@bp.get("/<slug>/procedimientos/obsoletos/")
@login_required
def listado_obsoletos(slug: str):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    if not user_can_view_sgi_obsoletos(u):
        flash("No tenés permiso para ver documentos obsoletos.", "warning")
        return redirect(url_for("sgi.listado_procedimientos", slug=slug))
    tipo, _ = _resolve_tipo(slug)
    args = doc_svc.filter_args_from_request(request.args, tipo_fijo=tipo)
    rows = proc_svc.fetch_list_visual(args, tipo=tipo or "", incluir_obsoletos=True)
    proc_svc.ensure_list_visual_nombres_mayusculas(rows)
    rows = [r for r in rows if r.estado == "obsoleto"]

    return render_template(
        "sgi/procedure_obsoletos.html",
        slug=slug,
        tipo=tipo,
        tipo_label=TIPO_LABELS.get(tipo or "", tipo or ""),
        rows=rows,
        filtros=args,
        estados_labels=ESTADO_LABELS,
    )


@bp.get("/<slug>/procedimientos/eliminados/")
@login_required
def listado_eliminados(slug: str):
    u, redir = _require_edit()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    if not proc_svc.tipo_soporta_visual(tipo):
        return redirect(url_for("sgi.listado", slug=slug))

    args = doc_svc.filter_args_from_request(request.args, tipo_fijo=tipo)
    rows = proc_svc.fetch_list_visual_eliminados(args, tipo=tipo or "")

    return render_template(
        "sgi/procedure_eliminados.html",
        slug=slug,
        tipo=tipo,
        tipo_label=TIPO_LABELS.get(tipo or "", tipo or ""),
        rows=rows,
        filtros=args,
        estados_labels=ESTADO_LABELS,
        documento_codigo_visible=doc_svc.documento_codigo_visible,
    )


@bp.post("/<slug>/procedimientos/<int:doc_id>/eliminar")
@login_required
def procedimiento_eliminar(slug: str, doc_id: int):
    u, redir = _require_edit()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo or not doc.es_procedimiento_visual:
        flash("Procedimiento no encontrado.", "danger")
        return redirect(url_for("sgi.listado_procedimientos", slug=slug))
    if not proc_svc.puede_eliminar_procedimiento(doc):
        flash("Solo se pueden eliminar procedimientos en borrador o en curso de revisión.", "warning")
        return redirect(url_for("sgi.listado_procedimientos", slug=slug))

    ok, msg = doc_svc.delete_documento(doc_id, user_display_name(u), actor=u)
    flash(msg, "success" if ok else "danger")
    dest = url_for("sgi.listado_eliminados", slug=slug) if ok else url_for("sgi.listado_procedimientos", slug=slug)
    return redirect(dest)


@bp.post("/<slug>/procedimientos/<int:doc_id>/recuperar")
@login_required
def procedimiento_recuperar(slug: str, doc_id: int):
    u, redir = _require_edit()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id, incluir_eliminados=True)
    if doc is None or doc.tipo != tipo or not doc.es_procedimiento_visual:
        flash("Procedimiento no encontrado.", "danger")
        return redirect(url_for("sgi.listado_eliminados", slug=slug))

    ok, msg = doc_svc.restore_documento(doc_id, user_display_name(u), actor=u)
    flash(msg, "success" if ok else "danger")
    dest = url_for("sgi.listado_procedimientos", slug=slug) if ok else url_for("sgi.listado_eliminados", slug=slug)
    return redirect(dest)


@bp.route("/<slug>/procedimientos/nuevo", methods=["GET", "POST"])
@login_required
def procedimiento_nuevo(slug: str):
    u, redir = _require_edit()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    if not proc_svc.tipo_soporta_visual(tipo):
        return redirect(url_for("sgi.nuevo", slug=slug))

    titulo = (request.args.get("titulo") or request.form.get("titulo") or "Nuevo procedimiento").strip()
    doc, rev, err = proc_svc.create_procedimiento_visual(tipo or "", u.id, user_display_name(u), titulo=titulo, actor=u)
    if err:
        flash(err, "danger")
        return redirect(url_for("sgi.listado_procedimientos", slug=slug))
    flash(f"Procedimiento {doc.codigo} creado.", "success")
    return redirect(url_for("sgi.procedimiento_editor", slug=slug, doc_id=doc.id, rev_id=rev.id))


@bp.route("/<slug>/procedimientos/<int:doc_id>/editor")
@bp.route("/<slug>/procedimientos/<int:doc_id>/editor/<int:rev_id>")
@login_required
def procedimiento_editor(slug: str, doc_id: int, rev_id: int | None = None):
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo or not doc.es_procedimiento_visual:
        flash("Procedimiento no encontrado.", "danger")
        return redirect(url_for("sgi.listado_procedimientos", slug=slug))
    if doc_svc.documento_esta_eliminado(doc):
        flash("Este procedimiento está en la papelera. Recuperalo desde «Documentos eliminados».", "warning")
        return redirect(url_for("sgi.listado_eliminados", slug=slug))

    if rev_id:
        rev = proc_svc.get_revision(rev_id)
        if rev is None or rev.documento_id != doc.id:
            abort(404)
    else:
        rev = proc_svc.revision_en_trabajo(doc) or proc_svc.revision_actual(doc)
        if rev is None:
            abort(404)

    u, redir = _require_procedure_workflow(rev)
    if redir is not None:
        return redir

    puede_editar = user_can_edit_sgi_documentos(u)
    if not proc_svc.puede_ver_documento(doc, puede_editar=puede_editar, user=u):
        flash("Solo puede visualizarse la versión aprobada.", "warning")
        vig = proc_svc.revision_vigente_aprobada(doc)
        if vig:
            return redirect(url_for("sgi.procedimiento_vista", slug=slug, doc_id=doc_id, rev_id=vig.id))
        return redirect(url_for("sgi.listado_procedimientos", slug=slug))

    if anexo_svc.documento_es_especial(doc):
        tc = anexo_svc.normalize_tipo_contenido(doc.tipo_contenido)
        item = anexo_svc.documento_view_item(doc, rev)
        wf = _special_doc_editor_context(slug, doc, rev, u, puede_editar)
        if tc == ANEXO_TIPO_DOCUMENTO:
            vista_tipo = proc_svc.anexo_vista_tipo(doc.archivo_path) if doc.archivo_path else None
            archivo_nombre = proc_svc.anexo_archivo_nombre(doc.archivo_path) if doc.archivo_path else None
            return render_template(
                "sgi/anexo_document_editor.html",
                anexo=item,
                standalone=True,
                payload=anexo_svc.documento_payload_for_view(doc, rev),
                secciones=PROCEDIMIENTO_SECCIONES,
                payload_json=json.dumps(anexo_svc.documento_payload_for_view(doc, rev), ensure_ascii=False),
                vista_tipo=vista_tipo,
                archivo_nombre=archivo_nombre,
                **_procedure_render_kwargs(**wf),
            )
        if tc == ANEXO_TIPO_ORGANIGRAMA:
            data = anexo_svc.parse_documento_contenido(doc, rev)
            editor_data = anexo_svc.organigrama_prepare_editor_data(data)
            return render_template(
                "sgi/anexo_organigrama_editor.html",
                anexo=item,
                standalone=True,
                nodes=editor_data["nodes"],
                org_layout=editor_data["layout"],
                usuarios=anexo_svc.organigrama_usuarios_opciones(),
                nodes_json=json.dumps(editor_data["nodes"], ensure_ascii=False),
                links_json=json.dumps(editor_data["links"], ensure_ascii=False),
                usuarios_json=json.dumps(anexo_svc.organigrama_usuarios_opciones(), ensure_ascii=False),
                **_procedure_render_kwargs(**wf),
            )
        if tc == ANEXO_TIPO_ARCHIVO:
            vista_tipo = proc_svc.anexo_vista_tipo(doc.archivo_path) if doc.archivo_path else None
            archivo_nombre = proc_svc.anexo_archivo_nombre(doc.archivo_path) if doc.archivo_path else None
            return render_template(
                "sgi/anexo_archivo_editor.html",
                anexo=item,
                standalone=True,
                vista_tipo=vista_tipo,
                archivo_nombre=archivo_nombre,
                **_procedure_render_kwargs(**wf),
            )
        flash("Este documento solo admite visualización.", "info")
        return redirect(url_for("sgi.procedimiento_vista", slug=slug, doc_id=doc.id, rev_id=rev.id))

    payload = proc_svc.revision_to_payload(rev)
    puede_marcar_revisado = proc_svc.user_can_marcar_revisado(u, rev)
    puede_aprobar = proc_svc.user_can_aprobar_revision(u, rev)
    puede_reenviar_aviso = proc_svc.user_can_reenviar_aviso(u, rev)
    solo_lectura = not puede_editar or rev.estado not in ("borrador", "en_revision")
    if rev.estado in ("en_revision", "revisado") and (puede_marcar_revisado or puede_aprobar):
        solo_lectura = True

    return render_template(
        "sgi/procedure_editor.html",
        **_procedure_render_kwargs(
            slug=slug,
            tipo=tipo,
            tipo_label=TIPO_LABELS.get(tipo or "", tipo or ""),
            tipo_caratula=TIPO_CARATULA_LABELS.get(tipo or "", "PROCEDIMIENTO"),
            doc=doc,
            rev=rev,
            payload_json=json.dumps(payload, ensure_ascii=False),
            secciones=PROCEDIMIENTO_SECCIONES,
            estados_labels=ESTADO_LABELS,
            solo_lectura=solo_lectura,
            puede_editar=puede_editar,
            puede_marcar_revisado=puede_marcar_revisado,
            puede_aprobar=puede_aprobar,
            puede_reenviar_aviso=puede_reenviar_aviso,
            correo_aviso_editable=puede_reenviar_aviso,
            perfiles_aplica=perfil_svc.perfiles_aplica_documento(doc.id),
            perfiles_opciones=perfil_svc.SGI_PERFILES_APLICABLES_LABELS,
        ),
    )


@bp.get("/<slug>/procedimientos/<int:doc_id>/vista")
@bp.get("/<slug>/procedimientos/<int:doc_id>/vista/<int:rev_id>")
@login_required
def procedimiento_vista(slug: str, doc_id: int, rev_id: int | None = None):
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        abort(404)
    if doc_svc.documento_esta_eliminado(doc):
        flash("Este procedimiento está en la papelera.", "warning")
        return redirect(url_for("sgi.listado_eliminados", slug=slug))
    u, redir = _require_procedure_read(doc)
    if redir is not None:
        return redir

    puede_editar = user_can_edit_sgi_documentos(u)
    if rev_id:
        rev = proc_svc.get_revision(rev_id)
    else:
        rev = proc_svc.revision_vigente_aprobada(doc) or proc_svc.revision_actual(doc)
    if rev is None or rev.documento_id != doc.id:
        abort(404)
    if not puede_editar and rev.estado not in ("aprobado", "vigente"):
        flash("No tenés permiso para ver esta versión.", "warning")
        return redirect(url_for("main.dashboard"))
    if not puede_editar and not proc_svc.documento_accesible_por_perfil(u, doc):
        flash("Este procedimiento no está asignado a tu perfil.", "warning")
        return redirect(url_for("main.dashboard"))

    if anexo_svc.documento_es_especial(doc):
        tc = anexo_svc.normalize_tipo_contenido(doc.tipo_contenido)
        item = anexo_svc.documento_view_item(doc, rev)
        if tc == ANEXO_TIPO_DOCUMENTO:
            return render_template(
                "sgi/anexo_document_view.html",
                **_procedure_render_kwargs(
                    slug=slug,
                    doc=doc,
                    rev=rev,
                    anexo=item,
                    standalone=True,
                    payload=anexo_svc.documento_payload_for_view(doc, rev),
                    secciones=PROCEDIMIENTO_SECCIONES,
                    puede_editar=puede_editar,
                ),
            )
        if tc == ANEXO_TIPO_ORGANIGRAMA:
            org_ctx = anexo_svc.organigrama_view_context(doc=doc, rev=rev)
            return render_template(
                "sgi/anexo_organigrama.html",
                slug=slug,
                doc=doc,
                rev=rev,
                anexo=item,
                standalone=True,
                puede_editar=puede_editar,
                **_procedure_render_kwargs(slug=slug, doc=doc, rev=rev, puede_editar=puede_editar),
                **org_ctx,
            )
        if not doc.archivo_path:
            abort(404)
        if doc_svc.attachment_absolute_path(doc.archivo_path) is None:
            abort(404)
        return render_template(
            "sgi/anexo_view.html",
            slug=slug,
            doc=doc,
            rev=rev,
            anexo=item,
            standalone=True,
            vista_tipo=proc_svc.anexo_vista_tipo(doc.archivo_path),
            archivo_nombre=proc_svc.anexo_archivo_nombre(doc.archivo_path),
            **_procedure_render_kwargs(
                slug=slug,
                doc=doc,
                rev=rev,
                puede_editar=puede_editar,
            ),
        )

    return render_template(
        "sgi/procedure_view.html",
        **_procedure_render_kwargs(
            slug=slug,
            doc=doc,
            rev=rev,
            tipo_caratula=TIPO_CARATULA_LABELS.get(doc.tipo or "", "PROCEDIMIENTO"),
            payload=proc_svc.revision_to_payload(rev),
            secciones=PROCEDIMIENTO_SECCIONES,
            estados_labels=ESTADO_LABELS,
            puede_editar=puede_editar,
        ),
    )


@bp.post("/<slug>/procedimientos/<int:doc_id>/revision/<int:rev_id>/guardar")
@login_required
def procedimiento_guardar(slug: str, doc_id: int, rev_id: int):
    rev = proc_svc.get_revision(rev_id)
    if rev is None or rev.documento_id != doc_id:
        return jsonify({"ok": False, "error": "no_encontrado"}), 404

    u = current_user()
    if u is None:
        return jsonify({"ok": False, "error": "sin_permiso"}), 403

    data = request.get_json(silent=True) or {}
    label = user_display_name(u)

    if user_can_edit_sgi_documentos(u):
        u_edit, redir = _require_edit()
        if redir is not None:
            return jsonify({"ok": False, "error": "sin_permiso"}), 403
        tipo, _ = _resolve_tipo(slug)
        doc = doc_svc.get_documento(doc_id)
        if doc is None or doc.tipo != tipo:
            return jsonify({"ok": False, "error": "no_encontrado"}), 404
        if anexo_svc.documento_es_especial(doc):
            ok, msg = proc_svc.save_revision_caratula_only(rev_id, data, u.id, label)
            return jsonify({"ok": ok, "message": msg, "control_cambios": []}), (200 if ok else 400)
        ok, msg, control_cambios = proc_svc.save_revision_content(
            rev_id, data, u.id, label, actor=u
        )
        return jsonify({"ok": ok, "message": msg, "control_cambios": control_cambios}), (200 if ok else 400)

    if proc_svc.user_can_marcar_revisado(u, rev) and rev.estado == ESTADO_EN_REVISION:
        ok, msg = proc_svc.save_workflow_caratula(rev_id, data, u.id, label)
        return jsonify({"ok": ok, "message": msg, "control_cambios": []}), (200 if ok else 400)

    return jsonify({"ok": False, "error": "sin_permiso"}), 403


@bp.post("/<slug>/procedimientos/<int:doc_id>/revision/<int:rev_id>/contenido")
@login_required
def procedimiento_guardar_contenido(slug: str, doc_id: int, rev_id: int):
    u, redir = _require_edit()
    if redir is not None:
        return jsonify({"ok": False, "error": "sin_permiso"}), 403
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        return jsonify({"ok": False, "error": "no_encontrado"}), 404
    data = request.get_json(silent=True) or {}
    ok, msg = anexo_svc.save_documento_contenido(doc_id, rev_id, data)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@bp.post("/<slug>/procedimientos/<int:doc_id>/archivo")
@login_required
def procedimiento_upload_archivo(slug: str, doc_id: int):
    u, redir = _require_edit()
    if redir is not None:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "error": "sin_permiso"}), 403
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        return jsonify({"ok": False, "message": "Documento no encontrado."}), 404
    f = request.files.get("archivo")
    ok, msg = proc_svc.save_documento_archivo(
        doc_id,
        f,
        u.id,
        actor_label=user_display_name(u),
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        extra: dict = {}
        if ok:
            doc = doc_svc.get_documento(doc_id)
            if doc is not None:
                extra = {
                    "archivo_nombre": proc_svc.anexo_archivo_nombre(doc.archivo_path),
                    "vista_tipo": proc_svc.anexo_vista_tipo(doc.archivo_path),
                }
        return jsonify({"ok": ok, "message": msg, **extra}), (200 if ok else 400)
    flash(msg, "success" if ok else "danger")
    return redirect(request.referrer or url_for("sgi.listado_procedimientos", slug=slug))


@bp.get("/<slug>/procedimientos/<int:doc_id>/archivo")
@login_required
def procedimiento_archivo(slug: str, doc_id: int):
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        abort(404)
    u, redir = _require_procedure_read(doc)
    if redir is not None:
        return redir
    if not doc.archivo_path:
        abort(404)
    path = doc_svc.attachment_absolute_path(doc.archivo_path)
    if path is None:
        abort(404)
    inline = request.args.get("inline", "").strip().lower() in ("1", "true", "yes")
    vista = proc_svc.anexo_vista_tipo(doc.archivo_path)
    as_attachment = not (inline and vista in ("image", "pdf"))
    return send_file(
        path,
        as_attachment=as_attachment,
        download_name=path.name,
        mimetype=proc_svc.anexo_send_mimetype(path),
        max_age=0,
    )


@bp.post("/<slug>/procedimientos/<int:doc_id>/revision/<int:rev_id>/workflow")
@login_required
def procedimiento_workflow(slug: str, doc_id: int, rev_id: int):
    rev = proc_svc.get_revision(rev_id)
    if rev is None or rev.documento_id != doc_id:
        return jsonify({"ok": False, "message": "Revisión no encontrada."}), 404

    u, redir = _require_procedure_workflow(rev)
    if redir is not None:
        return jsonify({"ok": False, "error": "sin_permiso"}), 403

    payload = request.get_json(silent=True) or {}
    accion = (request.form.get("accion") or payload.get("accion") or "") or ""
    accion = accion.strip().lower()
    label = user_display_name(u)

    if accion == "enviar_revision":
        if not user_can_edit_sgi_documentos(u):
            return jsonify({"ok": False, "error": "sin_permiso"}), 403
        ok, msg = proc_svc.enviar_a_revision(rev_id, u.id, label)
    elif accion == "marcar_revisado":
        if not proc_svc.user_can_marcar_revisado(u, rev):
            return jsonify({"ok": False, "error": "sin_permiso"}), 403
        if any(k in payload for k in ("aprobo", "aprobador_correo", "reviso", "revisor_correo")):
            proc_svc.save_workflow_caratula(rev_id, payload, u.id, label)
            rev = proc_svc.get_revision(rev_id)
            if rev is None:
                return jsonify({"ok": False, "message": "Revisión no encontrada."}), 404
        ok, msg = proc_svc.marcar_como_revisado(rev_id, u.id, label)
    elif accion == "aprobar":
        if not proc_svc.user_can_aprobar_revision(u, rev):
            return jsonify({"ok": False, "error": "sin_permiso"}), 403
        ok, msg = proc_svc.aprobar_revision(rev_id, u.id, label)
    elif accion == "nueva_revision":
        if not user_can_edit_sgi_documentos(u):
            return jsonify({"ok": False, "error": "sin_permiso"}), 403
        rev_new, err = proc_svc.crear_nueva_revision(doc_id, u.id, label)
        if err:
            return jsonify({"ok": False, "message": err}), 400
        return jsonify({"ok": True, "message": "Nueva revisión creada.", "rev_id": rev_new.id})
    elif accion == "reenviar_aviso":
        if not proc_svc.user_can_reenviar_aviso(u, rev):
            return jsonify({"ok": False, "error": "sin_permiso"}), 403
        ok, msg = proc_svc.reenviar_aviso_workflow(rev_id, payload)
    else:
        return jsonify({"ok": False, "message": "Acción no reconocida."}), 400

    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@bp.get("/<slug>/procedimientos/<int:doc_id>/historial")
@login_required
def procedimiento_historial(slug: str, doc_id: int):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        abort(404)
    revs = proc_svc.historial_revisiones(doc_id)
    return render_template(
        "sgi/procedure_historial.html",
        slug=slug,
        doc=doc,
        revisiones=revs,
        estados_labels=ESTADO_LABELS,
        puede_editar=user_can_edit_sgi_documentos(u),
    )


@bp.get("/<slug>/procedimientos/<int:doc_id>/revision/<int:rev_id>/export/<fmt>")
@login_required
def procedimiento_export(slug: str, doc_id: int, rev_id: int, fmt: str):
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    rev = proc_svc.get_revision(rev_id)
    if doc is None or rev is None or rev.documento_id != doc.id:
        abort(404)
    u, redir = _require_procedure_read(doc)
    if redir is not None:
        return redir

    puede_editar = user_can_edit_sgi_documentos(u)
    if rev.estado not in ("aprobado", "vigente") and not puede_editar:
        abort(403)
    if not puede_editar and not proc_svc.documento_accesible_por_perfil(u, doc):
        abort(403)

    html = render_template(
        "sgi/procedure_print.html",
        **_procedure_render_kwargs(
            doc=doc,
            rev=rev,
            tipo_caratula=TIPO_CARATULA_LABELS.get(doc.tipo or "", "PROCEDIMIENTO"),
            payload=proc_svc.revision_to_payload(rev),
            secciones=PROCEDIMIENTO_SECCIONES,
            para_export=True,
        ),
    )
    safe_name = f"{doc.codigo}_{rev.revision_label}".replace(" ", "_").replace(".", "")

    if fmt == "pdf":
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}
    if fmt == "word":
        return (
            html,
            200,
            {
                "Content-Type": "application/msword",
                "Content-Disposition": f'attachment; filename="{safe_name}.doc"',
            },
        )
    abort(404)


@bp.post("/<slug>/procedimientos/anexo/<int:anexo_id>/archivo")
@login_required
def procedimiento_anexo_upload(slug: str, anexo_id: int):
    u, redir = _require_edit()
    if redir is not None:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "error": "sin_permiso"}), 403
        return redir
    f = request.files.get("archivo")
    ok, msg = proc_svc.save_anexo_file(anexo_id, f, u.id)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        extra: dict = {}
        if ok:
            anexo, _ = proc_svc.get_anexo_for_access(anexo_id)
            if anexo is not None:
                extra = {
                    "archivo_nombre": proc_svc.anexo_archivo_nombre(anexo.archivo_path),
                    "vista_tipo": proc_svc.anexo_vista_tipo(anexo.archivo_path),
                }
        return jsonify({"ok": ok, "message": msg, **extra}), (200 if ok else 400)
    flash(msg, "success" if ok else "danger")
    return redirect(request.referrer or url_for("sgi.hub"))


def _anexo_access(anexo_id: int, slug: str):
    tipo, _ = _resolve_tipo(slug)
    anexo, err = proc_svc.get_anexo_for_access(anexo_id, tipo_esperado=tipo)
    if anexo is None:
        abort(404)
    rev = anexo.proc_revision
    doc = rev.documento
    u, redir = _require_procedure_read(doc)
    if redir is not None:
        return None, None, None, redir
    if not user_can_edit_sgi_documentos(u) and rev.estado not in ("aprobado", "vigente"):
        abort(404)
    if not user_can_edit_sgi_documentos(u) and not proc_svc.documento_accesible_por_perfil(u, doc):
        abort(404)
    return anexo, doc, rev, None


@bp.get("/<slug>/procedimientos/anexo/<int:anexo_id>/ver")
@login_required
def procedimiento_anexo_ver(slug: str, anexo_id: int):
    anexo, doc, rev, redir = _anexo_access(anexo_id, slug)
    if redir is not None:
        return redir
    puede_editar = user_can_edit_sgi_documentos(current_user())
    tipo = (anexo.tipo_contenido or ANEXO_TIPO_ARCHIVO).lower()

    if tipo == ANEXO_TIPO_DOCUMENTO:
        return render_template(
            "sgi/anexo_document_view.html",
            **_procedure_render_kwargs(
                slug=slug,
                doc=doc,
                rev=rev,
                anexo=anexo,
                payload=anexo_svc.documento_payload_for_view(anexo),
                secciones=PROCEDIMIENTO_SECCIONES,
                puede_editar=puede_editar,
            ),
        )
    if tipo == ANEXO_TIPO_ORGANIGRAMA:
        org_ctx = anexo_svc.organigrama_view_context(anexo=anexo)
        return render_template(
            "sgi/anexo_organigrama.html",
            slug=slug,
            doc=doc,
            rev=rev,
            anexo=anexo,
            puede_editar=puede_editar,
            **org_ctx,
        )

    if not anexo.archivo_path:
        abort(404)
    path = proc_svc.anexo_absolute_path(anexo.archivo_path)
    if path is None:
        abort(404)
    vista = proc_svc.anexo_vista_tipo(anexo.archivo_path)
    return render_template(
        "sgi/anexo_view.html",
        slug=slug,
        doc=doc,
        rev=rev,
        anexo=anexo,
        vista_tipo=vista,
        archivo_nombre=proc_svc.anexo_archivo_nombre(anexo.archivo_path),
    )


@bp.get("/<slug>/procedimientos/anexo/<int:anexo_id>/editor")
@login_required
def procedimiento_anexo_editor(slug: str, anexo_id: int):
    u, redir = _require_edit()
    if redir is not None:
        return redir
    anexo, doc, rev, redir = _anexo_access(anexo_id, slug)
    if redir is not None:
        return redir
    tipo = (anexo.tipo_contenido or ANEXO_TIPO_ARCHIVO).lower()
    if tipo == ANEXO_TIPO_DOCUMENTO:
        return render_template(
            "sgi/anexo_document_editor.html",
            slug=slug,
            doc=doc,
            rev=rev,
            anexo=anexo,
            payload=anexo_svc.documento_payload_for_view(anexo),
            secciones=PROCEDIMIENTO_SECCIONES,
            payload_json=json.dumps(anexo_svc.documento_payload_for_view(anexo), ensure_ascii=False),
        )
    if tipo == ANEXO_TIPO_ORGANIGRAMA:
        data = anexo_svc.parse_anexo_contenido(anexo)
        editor_data = anexo_svc.organigrama_prepare_editor_data(data)
        return render_template(
            "sgi/anexo_organigrama_editor.html",
            slug=slug,
            doc=doc,
            rev=rev,
            anexo=anexo,
            nodes=editor_data["nodes"],
            org_layout=editor_data["layout"],
            usuarios=anexo_svc.organigrama_usuarios_opciones(),
            nodes_json=json.dumps(editor_data["nodes"], ensure_ascii=False),
            links_json=json.dumps(editor_data["links"], ensure_ascii=False),
            usuarios_json=json.dumps(anexo_svc.organigrama_usuarios_opciones(), ensure_ascii=False),
        )
    abort(404)


@bp.post("/<slug>/procedimientos/anexo/<int:anexo_id>/contenido")
@login_required
def procedimiento_anexo_guardar_contenido(slug: str, anexo_id: int):
    u, redir = _require_edit()
    if redir is not None:
        return jsonify({"ok": False, "error": "sin_permiso"}), 403
    anexo, _, _, redir = _anexo_access(anexo_id, slug)
    if redir is not None:
        return jsonify({"ok": False, "error": "sin_permiso"}), 403
    data = request.get_json(silent=True) or {}
    ok, msg = anexo_svc.save_anexo_contenido(anexo_id, data)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@bp.get("/<slug>/procedimientos/anexo/<int:anexo_id>/archivo")
@login_required
def procedimiento_anexo_download(slug: str, anexo_id: int):
    anexo, _, _, redir = _anexo_access(anexo_id, slug)
    if redir is not None:
        return redir
    path = proc_svc.anexo_absolute_path(anexo.archivo_path)
    if path is None:
        abort(404)
    inline = request.args.get("inline", "").strip().lower() in ("1", "true", "yes")
    vista = proc_svc.anexo_vista_tipo(anexo.archivo_path)
    as_attachment = not (inline and vista in ("image", "pdf"))
    return send_file(
        path,
        as_attachment=as_attachment,
        download_name=path.name,
        mimetype=proc_svc.anexo_send_mimetype(path),
        max_age=0,
    )
