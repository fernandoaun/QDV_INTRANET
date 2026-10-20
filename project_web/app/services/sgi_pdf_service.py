"""PDF de un procedimiento SGI generado en el servidor (WeasyPrint), para adjuntarlo a los avisos de difusión.

Usa la misma plantilla que «Imprimir / PDF» con una hoja de estilos propia: encabezado en cada página
con «Página x de y», y control de cambios, firmas y vigencia al pie de la primera hoja.
"""
from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import current_app, has_request_context, render_template
from sqlalchemy import select

from app.extensions import db
from app.models.sgi import PROCEDIMIENTO_SECCIONES, TIPO_CARATULA_LABELS, SgiDocumento, SgiProcedimientoRevision

log = logging.getLogger(__name__)

_BASE = "http://qdv.local/"


def nombre_archivo(doc: SgiDocumento, rev: SgiProcedimientoRevision) -> str:
    base = f"{doc.codigo or 'documento'} {rev.revision_label or ''} {doc.titulo or ''}".strip()
    base = re.sub(r"[^\w\-. ]+", "", base, flags=re.UNICODE)
    return re.sub(r"\s+", " ", base)[:120].strip() + ".pdf"


def _fetcher(app: Any):
    from weasyprint import default_url_fetcher

    static_root = Path(app.static_folder or "").resolve()

    def fetch(url: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if not url.startswith(_BASE):
            if url.startswith("data:"):
                return default_url_fetcher(url, *args, **kwargs)
            raise ValueError(f"URL externa no permitida en el PDF: {url[:80]}")
        path = urlsplit(url).path
        mime = mimetypes.guess_type(path)[0]
        if path.startswith("/static/"):
            f = (static_root / path[len("/static/"):]).resolve()
            if static_root not in f.parents or not f.is_file():
                raise ValueError(f"estático inexistente: {path}")
            return {"string": f.read_bytes(), "mime_type": mime}
        # Otras rutas del sistema (p. ej. la firma del gerente): se piden a la app con un administrador.
        from app.models import User

        admin = db.session.scalar(select(User).where(User.is_admin.is_(True), User.activo.is_(True)).order_by(User.id).limit(1))
        client = app.test_client()
        if admin is not None:
            with client.session_transaction() as s:
                s["user_id"] = int(admin.id)
        r = client.get(path)
        if r.status_code != 200:
            raise ValueError(f"{path} → HTTP {r.status_code}")
        return {"string": r.get_data(), "mime_type": (r.mimetype or mime)}

    return fetch


def procedimiento_pdf(doc: SgiDocumento, rev: SgiProcedimientoRevision) -> bytes:
    """Bytes del PDF del procedimiento (revisión indicada). Levanta excepción si no se puede generar."""
    from weasyprint import HTML

    from app.services import sgi_procedimiento_service as proc_svc
    from app.web.modules.sgi.procedure_routes import _procedure_render_kwargs

    app = current_app._get_current_object()

    def _html() -> str:
        return render_template(
            "sgi/procedure_print.html",
            **_procedure_render_kwargs(
                doc=doc,
                rev=rev,
                tipo_caratula=TIPO_CARATULA_LABELS.get(doc.tipo or "", "PROCEDIMIENTO"),
                payload=proc_svc.revision_to_payload(rev),
                secciones=PROCEDIMIENTO_SECCIONES,
                para_export=False,
                pdf=True,
            ),
        )

    if has_request_context():
        html = _html()
    else:
        with app.test_request_context():
            html = _html()
    return HTML(string=html, base_url=_BASE, url_fetcher=_fetcher(app)).write_pdf()


def adjunto_difusion(doc: SgiDocumento, rev: SgiProcedimientoRevision) -> tuple[str, bytes, str] | None:
    """(nombre, bytes, mime) para adjuntar al aviso de difusión, o None si no se pudo generar.

    Documentos especiales (subidos como archivo) adjuntan el archivo si es PDF; los visuales, el PDF generado.
    """
    try:
        from app.services import sgi_anexo_service as anexo_svc

        if anexo_svc.documento_es_especial(doc):
            from app.services import sgi_service as doc_svc

            rel = (doc.archivo_path or "").strip()
            if not rel.lower().endswith(".pdf"):
                return None
            path = doc_svc.attachment_absolute_path(rel)
            if path is None or not Path(path).is_file():
                return None
            return (nombre_archivo(doc, rev), Path(path).read_bytes(), "application/pdf")
        return (nombre_archivo(doc, rev), procedimiento_pdf(doc, rev), "application/pdf")
    except Exception:
        log.exception("No se pudo generar el PDF de %s (%s)", doc.codigo, rev.revision_label)
        return None
