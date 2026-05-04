"""Subida y descarga de PDFs de referencia de análisis (por doc_key)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Response, abort, current_app, flash, redirect, request, send_file, url_for

from app.auth_utils import current_user, user_can
from app.extensions import db
from app.models import AppUploadedDocument
from app.services.analysis_ref_pdf import (
    analysis_ref_pdf_meta,
    analysis_ref_pdf_resolve_file_path,
    analysis_ref_pdf_storage_dir,
)
from app.web.modules.produccion.operativa_context import now_local


def _user_can_any_document_permission(u: Any, raw_permission: Any) -> bool:
    permissions = raw_permission if isinstance(raw_permission, (tuple, list, set, frozenset)) else (raw_permission,)
    return any(user_can(u, str(permission)) for permission in permissions)


def reference_pdf_safe_original_name(filename: str) -> str:
    base = Path(filename).name.strip()
    if not base:
        return "documento.pdf"
    return base[:200]


def validate_pdf_upload(fs: Any, max_bytes: int | None = None) -> str:
    if fs is None or not getattr(fs, "filename", None):
        raise ValueError("Seleccioná un archivo PDF.")
    raw = (fs.filename or "").strip()
    if not raw.lower().endswith(".pdf"):
        raise ValueError("Solo se permiten archivos PDF.")
    mb = max_bytes
    if mb is None:
        try:
            mb = int(current_app.config.get("ANALYSIS_REF_PDF_MAX_BYTES") or (15 * 1024 * 1024))
        except (TypeError, ValueError):
            mb = 15 * 1024 * 1024
    if mb and mb > 0:
        fs.seek(0)
        blob = fs.read(mb + 1)
        fs.seek(0)
        if len(blob) > mb:
            raise ValueError("El archivo supera el tamaño máximo permitido para PDF.")
    ct = (getattr(fs, "content_type", None) or "").lower()
    if ct and "pdf" not in ct:
        raise ValueError("El archivo no es un PDF válido (tipo MIME).")
    head = fs.read(5)
    fs.seek(0)
    if len(head) < 4 or head[:4] != b"%PDF":
        raise ValueError("El contenido no es un PDF válido.")
    return reference_pdf_safe_original_name(raw)


def analysis_ref_pdf_redirect(meta: dict[str, Any]) -> Response:
    ep = meta.get("redirect_endpoint") or "produccion.salmuera"
    return redirect(request.referrer or url_for(ep))


def handle_analysis_ref_pdf_request(doc_key: str) -> Response:
    meta = analysis_ref_pdf_meta(doc_key)
    if meta is None:
        abort(404)

    u = current_user()
    if u is None or not _user_can_any_document_permission(u, meta["permission"]):
        flash("No tenés permiso para acceder a este documento.", "danger")
        return redirect(url_for("main.dashboard"))

    label = str(meta.get("flash_label") or doc_key)
    store_dir = analysis_ref_pdf_storage_dir(doc_key)

    if request.method == "GET":
        row = db.session.get(AppUploadedDocument, doc_key)
        resolved = analysis_ref_pdf_resolve_file_path(doc_key, row)
        if resolved is None:
            abort(404)
        return send_file(
            resolved,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=(row.original_filename or f"{doc_key}.pdf"),
        )

    if u.is_admin is not True:
        flash(f"Solo administradores pueden subir o eliminar el PDF de {label}.", "danger")
        return analysis_ref_pdf_redirect(meta)

    action = (request.form.get("action") or "").strip()
    if action == "delete":
        row = db.session.get(AppUploadedDocument, doc_key)
        if row:
            old_fp = analysis_ref_pdf_resolve_file_path(doc_key, row)
            if old_fp is not None:
                try:
                    old_fp.unlink(missing_ok=True)
                except OSError:
                    pass
            db.session.delete(row)
            db.session.commit()
            flash(f"PDF de {label} eliminado.", "info")
        else:
            flash("No había PDF cargado.", "warning")
        return analysis_ref_pdf_redirect(meta)

    fs = request.files.get("pdf")
    if fs is None or not fs.filename:
        flash("Seleccioná un archivo PDF.", "warning")
        return analysis_ref_pdf_redirect(meta)

    try:
        orig_name = validate_pdf_upload(fs)
    except ValueError as e:
        flash(str(e), "danger")
        return analysis_ref_pdf_redirect(meta)

    stored = f"{uuid4().hex}.pdf"
    dest = store_dir / stored
    row = db.session.get(AppUploadedDocument, doc_key)
    if row:
        old_fp = analysis_ref_pdf_resolve_file_path(doc_key, row)
        if old_fp is not None:
            try:
                old_fp.unlink(missing_ok=True)
            except OSError:
                pass
        row.stored_filename = stored
        row.original_filename = orig_name
        row.updated_at_iso = now_local().isoformat(timespec="seconds")
    else:
        db.session.add(
            AppUploadedDocument(
                doc_key=doc_key,
                stored_filename=stored,
                original_filename=orig_name,
                updated_at_iso=now_local().isoformat(timespec="seconds"),
            )
        )
    try:
        fs.save(str(dest))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        flash(str(e), "danger")
        return analysis_ref_pdf_redirect(meta)
    flash(f"PDF de {label} guardado.", "success")
    return analysis_ref_pdf_redirect(meta)
