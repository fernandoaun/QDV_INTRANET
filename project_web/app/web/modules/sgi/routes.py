from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, session, url_for

from app.auth_utils import (
    current_user,
    login_required,
    user_can_access_sgi,
    user_can_delete_sgi_documentos,
    user_can_edit_sgi_documentos,
    user_display_name,
)
from app.models.sgi import ESTADO_LABELS, TIPO_LABELS, TIPOS_DOCUMENTO
from app.services import sgi_notification_service as sgi_notif_svc
from app.services import sgi_procedimiento_service as proc_svc
from app.services import sgi_service as svs

bp = Blueprint("sgi", __name__, url_prefix="/sgi")


@bp.post("/notificaciones/visto")
@login_required
def notificaciones_mark_seen():
    u = current_user()
    if u is None:
        return "", 403
    raw = (request.form.get("up_to_id") or "").strip()
    up_to: int | None = None
    if raw:
        try:
            up_to = int(raw)
        except ValueError:
            up_to = None
    sgi_notif_svc.mark_sgi_notifications_seen(session, up_to_id=up_to)
    return "", 204


def _no_access():
    flash("No tenés permiso para acceder al módulo SGI.", "warning")
    return redirect(url_for("main.dashboard"))


def _no_mutate():
    flash("No tenés permiso para modificar documentos SGI.", "warning")
    return redirect(request.referrer or url_for("sgi.hub"))


def _no_delete():
    flash("No tenés permiso para eliminar documentos SGI.", "warning")
    return redirect(request.referrer or url_for("sgi.hub"))


def _require_view():
    u = current_user()
    if not user_can_access_sgi(u):
        return None, None, _no_access()
    return u, None, None


def _resolve_tipo(slug: str) -> tuple[str | None, object | None]:
    tipo = svs.tipo_from_slug(slug)
    if tipo is None:
        return None, abort(404)
    return tipo, None


@bp.get("/")
@login_required
def hub():
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    counts = svs.counts_by_tipo()
    return render_template(
        "sgi/hub.html",
        counts=counts,
        tipo_labels=TIPO_LABELS,
        puede_editar=user_can_edit_sgi_documentos(u),
    )


@bp.get("/<slug>/")
@login_required
def listado(slug: str):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    args = svs.filter_args_from_request(request.args, tipo_fijo=tipo)
    rows = svs.fetch_list(args)
    svs.ensure_list_nombres_mayusculas(rows)
    return render_template(
        "sgi/list.html",
        slug=slug,
        tipo=tipo,
        tipo_label=TIPO_LABELS.get(tipo or "", tipo or ""),
        rows=rows,
        filtros=args,
        estados_labels=ESTADO_LABELS,
        estado_visual_row=svs.estado_visual_row,
        puede_editar=user_can_edit_sgi_documentos(u),
        puede_eliminar=user_can_delete_sgi_documentos(u),
    )


@bp.get("/<slug>/export.xlsx")
@login_required
def export_xlsx(slug: str):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    args = svs.filter_args_from_request(request.args, tipo_fijo=tipo)
    rows = svs.fetch_list(args)
    bio = svs.build_export_xlsx(rows, tipo_label=TIPO_LABELS.get(tipo or "", slug))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return send_file(
        bio,
        as_attachment=True,
        download_name=f"sgi_{slug}_{ts}.xlsx",
        max_age=0,
    )


@bp.route("/<slug>/nuevo", methods=["GET", "POST"])
@login_required
def nuevo(slug: str):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    if not user_can_edit_sgi_documentos(u):
        return _no_mutate()
    tipo, _ = _resolve_tipo(slug)
    if request.method == "POST":
        row, err = svs.create_documento(
            dict(request.form),
            u.id,
            user_display_name(u),
            tipo_fijo=tipo,
            actor=u,
        )
        if err:
            flash(err, "danger")
            return render_template(
                "sgi/form.html",
                modo="nuevo",
                slug=slug,
                tipo=tipo,
                tipo_label=TIPO_LABELS.get(tipo or "", tipo or ""),
                form=request.form,
            )
        flash("Documento creado.", "success")
        f = request.files.get("archivo")
        if f and (f.filename or "").strip():
            ok_att, msg_att = svs.save_attachment(row.id, f, u.id, user_display_name(u), actor=u)
            flash(msg_att, "success" if ok_att else "warning")
        return redirect(url_for("sgi.detalle", slug=slug, doc_id=row.id))
    return render_template(
        "sgi/form.html",
        modo="nuevo",
        slug=slug,
        tipo=tipo,
        tipo_label=TIPO_LABELS.get(tipo or "", tipo or ""),
        form=None,
        estados_labels=ESTADO_LABELS,
    )


@bp.route("/<slug>/<int:doc_id>/editar", methods=["GET", "POST"])
@login_required
def editar(slug: str, doc_id: int):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = svs.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        flash("Documento no encontrado.", "danger")
        return redirect(url_for("sgi.listado", slug=slug))
    if not user_can_edit_sgi_documentos(u):
        return _no_mutate()
    if request.method == "POST":
        ok, msg = svs.update_documento(
            doc_id,
            dict(request.form),
            u.id,
            user_display_name(u),
            tipo_fijo=tipo,
            actor=u,
        )
        flash(msg, "success" if ok else "danger")
        if ok:
            f = request.files.get("archivo")
            if f and (f.filename or "").strip():
                ok_att, msg_att = svs.save_attachment(doc_id, f, u.id, user_display_name(u), actor=u)
                flash(msg_att, "success" if ok_att else "warning")
            return redirect(url_for("sgi.detalle", slug=slug, doc_id=doc_id))
    form_prefill = {
        "codigo": doc.codigo,
        "titulo": doc.titulo,
        "revision": doc.revision,
        "fecha_creacion_doc": doc.fecha_creacion_doc.isoformat() if doc.fecha_creacion_doc else "",
        "fecha_ultima_revision": doc.fecha_ultima_revision.isoformat() if doc.fecha_ultima_revision else "",
        "responsable_elaboracion": doc.responsable_elaboracion,
        "responsable_aprobacion": doc.responsable_aprobacion,
        "estado": doc.estado,
        "observaciones": doc.observaciones,
    }
    return render_template(
        "sgi/form.html",
        modo="editar",
        slug=slug,
        tipo=tipo,
        tipo_label=TIPO_LABELS.get(tipo or "", tipo or ""),
        doc=doc,
        form=form_prefill,
        estados_labels=ESTADO_LABELS,
    )


@bp.get("/<slug>/<int:doc_id>")
@login_required
def detalle(slug: str, doc_id: int):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = svs.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        flash("Documento no encontrado.", "danger")
        return redirect(url_for("sgi.listado", slug=slug))
    hist = svs.historial_for(doc_id)
    firma_gerente_url = proc_svc.firma_gerente_url_for_document(doc) if tipo == "MSGI" else None
    return render_template(
        "sgi/detail.html",
        slug=slug,
        tipo=tipo,
        tipo_label=TIPO_LABELS.get(tipo or "", tipo or ""),
        doc=doc,
        hist=hist,
        estados_labels=ESTADO_LABELS,
        estado_visual_row=svs.estado_visual_row,
        puede_editar=user_can_edit_sgi_documentos(u),
        puede_eliminar=user_can_delete_sgi_documentos(u) and svs.puede_eliminar_documento(doc),
        firma_gerente_url=firma_gerente_url,
        doc_aprobado=(doc.estado or "") in ("aprobado", "vigente"),
    )


@bp.post("/<slug>/<int:doc_id>/eliminar")
@login_required
def eliminar(slug: str, doc_id: int):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    if not user_can_delete_sgi_documentos(u):
        return _no_delete()
    tipo, _ = _resolve_tipo(slug)
    doc = svs.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        flash("Documento no encontrado.", "danger")
        return redirect(url_for("sgi.listado", slug=slug))
    if not svs.puede_eliminar_documento(doc):
        flash("Solo se pueden eliminar documentos en borrador o en curso de revisión.", "warning")
        return redirect(url_for("sgi.detalle", slug=slug, doc_id=doc_id))
    ok, msg = svs.delete_documento(doc_id, user_display_name(u), actor=u)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("sgi.listado", slug=slug))


@bp.route("/<slug>/<int:doc_id>/firma-gerente", methods=["GET", "POST"])
@login_required
def firma_gerente(slug: str, doc_id: int):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    if tipo != "MSGI":
        abort(404)
    doc = svs.get_documento(doc_id)
    if doc is None or doc.tipo != tipo:
        abort(404)

    if request.method == "POST":
        if not user_can_edit_sgi_documentos(u):
            return _no_mutate()
        f = request.files.get("firma") or request.files.get("archivo")
        ok, msg = proc_svc.save_firma_gerente_file(doc_id, f, u.id)
        flash(msg, "success" if ok else "danger")
        dest = request.referrer or url_for("sgi.detalle", slug=slug, doc_id=doc_id)
        return redirect(dest)

    path = proc_svc.firma_gerente_absolute_path(doc_id)
    if path is None:
        static_url = proc_svc.global_firma_gerente_static_url()
        if static_url:
            return redirect(static_url)
        abort(404)
    return send_file(path, max_age=3600)


@bp.get("/<slug>/<int:doc_id>/archivo")
@login_required
def adjunto_descargar(slug: str, doc_id: int):
    u, _, redir = _require_view()
    if redir is not None:
        return redir
    tipo, _ = _resolve_tipo(slug)
    doc = svs.get_documento(doc_id)
    if doc is None or doc.tipo != tipo or not doc.archivo_path:
        abort(404)
    path = svs.attachment_absolute_path(doc.archivo_path)
    if path is None:
        abort(404)
    inline = request.args.get("inline", "").strip().lower() in ("1", "true", "yes")
    return send_file(path, as_attachment=not inline, download_name=path.name if not inline else None, max_age=0)
