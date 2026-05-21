"""Rutas del generador visual de procedimientos (PG / PO)."""
from __future__ import annotations

import json

from pathlib import Path

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for

from app.auth_utils import (
    current_user,
    login_required,
    user_can_edit_sgi_documentos,
    user_can_view_sgi_obsoletos,
    user_display_name,
)
from app.models.sgi import ESTADO_LABELS, PROCEDIMIENTO_SECCIONES, TIPO_CARATULA_LABELS, TIPO_LABELS
from app.services import sgi_procedimiento_service as proc_svc
from app.services import sgi_service as doc_svc
from app.web.modules.sgi.routes import _no_access, _no_mutate, _require_view, _resolve_tipo, bp


def _custom_logo_url() -> str | None:
    """Si existe img/qdv-logo.png (o jpg), usarlo en lugar del SVG embebido."""
    static_root = Path(current_app.static_folder or "")
    for name in ("qdv-logo.png", "qdv-logo.jpg", "qdv-logo.jpeg", "qdv-logo.webp"):
        if (static_root / "img" / name).is_file():
            return url_for("static", filename=f"img/{name}")
    return None


def _procedure_render_kwargs(**extra: object) -> dict:
    return {"custom_logo_url": _custom_logo_url(), **extra}


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
    puede_editar = user_can_edit_sgi_documentos(u)
    if not puede_editar:
        rows = [r for r in rows if proc_svc.puede_ver_documento(r, puede_editar=False)]

    row_meta: dict[int, dict] = {}
    for r in rows:
        rev = proc_svc.revision_vigente_aprobada(r) or proc_svc.revision_en_trabajo(r) or proc_svc.revision_actual(r)
        row_meta[r.id] = {"rev_id": rev.id if rev else None}

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
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo or not doc.es_procedimiento_visual:
        flash("Procedimiento no encontrado.", "danger")
        return redirect(url_for("sgi.listado_procedimientos", slug=slug))

    puede_editar = user_can_edit_sgi_documentos(u)
    if not proc_svc.puede_ver_documento(doc, puede_editar=puede_editar):
        flash("Solo puede visualizarse la versión aprobada.", "warning")
        vig = proc_svc.revision_vigente_aprobada(doc)
        if vig:
            return redirect(url_for("sgi.procedimiento_vista", slug=slug, doc_id=doc_id, rev_id=vig.id))
        return redirect(url_for("sgi.listado_procedimientos", slug=slug))

    if rev_id:
        rev = proc_svc.get_revision(rev_id)
        if rev is None or rev.documento_id != doc.id:
            abort(404)
    else:
        rev = proc_svc.revision_en_trabajo(doc) or proc_svc.revision_actual(doc)
        if rev is None:
            abort(404)

    payload = proc_svc.revision_to_payload(rev)
    solo_lectura = not puede_editar or rev.estado not in ("borrador", "en_revision")

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
        ),
    )


@bp.get("/<slug>/procedimientos/<int:doc_id>/vista")
@bp.get("/<slug>/procedimientos/<int:doc_id>/vista/<int:rev_id>")
@login_required
def procedimiento_vista(slug: str, doc_id: int, rev_id: int | None = None):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        abort(404)

    puede_editar = user_can_edit_sgi_documentos(u)
    if rev_id:
        rev = proc_svc.get_revision(rev_id)
    else:
        rev = proc_svc.revision_vigente_aprobada(doc) or proc_svc.revision_actual(doc)
    if rev is None or rev.documento_id != doc.id:
        abort(404)
    if not puede_editar and rev.estado not in ("aprobado", "vigente"):
        flash("No tenés permiso para ver esta versión.", "warning")
        return redirect(url_for("sgi.listado_procedimientos", slug=slug))

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
    u, redir = _require_edit()
    if redir is not None:
        return jsonify({"ok": False, "error": "sin_permiso"}), 403
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        return jsonify({"ok": False, "error": "no_encontrado"}), 404

    data = request.get_json(silent=True) or {}
    ok, msg, control_cambios = proc_svc.save_revision_content(
        rev_id, data, u.id, user_display_name(u), actor=u
    )
    return jsonify({"ok": ok, "message": msg, "control_cambios": control_cambios}), (200 if ok else 400)


@bp.post("/<slug>/procedimientos/<int:doc_id>/revision/<int:rev_id>/workflow")
@login_required
def procedimiento_workflow(slug: str, doc_id: int, rev_id: int):
    u, redir = _require_edit()
    if redir is not None:
        return jsonify({"ok": False, "error": "sin_permiso"}), 403

    payload = request.get_json(silent=True) or {}
    accion = (request.form.get("accion") or payload.get("accion") or "") or ""
    accion = accion.strip().lower()
    label = user_display_name(u)

    if accion == "enviar_revision":
        ok, msg = proc_svc.enviar_a_revision(rev_id, u.id, label)
    elif accion == "aprobar":
        ok, msg = proc_svc.aprobar_revision(rev_id, u.id, label)
    elif accion == "nueva_revision":
        rev, err = proc_svc.crear_nueva_revision(doc_id, u.id, label)
        if err:
            return jsonify({"ok": False, "message": err}), 400
        return jsonify({"ok": True, "message": "Nueva revisión creada.", "rev_id": rev.id})
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
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = doc_svc.get_documento(doc_id)
    rev = proc_svc.get_revision(rev_id)
    if doc is None or rev is None or rev.documento_id != doc.id:
        abort(404)

    puede_editar = user_can_edit_sgi_documentos(u)
    if not proc_svc.puede_ver_documento(doc, puede_editar=puede_editar) and rev.estado not in ("aprobado", "vigente"):
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
        return redir
    f = request.files.get("archivo")
    ok, msg = proc_svc.save_anexo_file(anexo_id, f, u.id)
    flash(msg, "success" if ok else "danger")
    return redirect(request.referrer or url_for("sgi.hub"))


@bp.get("/<slug>/procedimientos/anexo/<int:anexo_id>/archivo")
@login_required
def procedimiento_anexo_download(slug: str, anexo_id: int):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    from app.extensions import db
    from app.models.sgi import SgiProcedimientoAnexo

    anexo = db.session.get(SgiProcedimientoAnexo, anexo_id)
    if anexo is None or not anexo.archivo_path:
        abort(404)
    path = proc_svc.anexo_absolute_path(anexo.archivo_path)
    if path is None:
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name, max_age=0)
