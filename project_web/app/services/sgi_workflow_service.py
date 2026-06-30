"""Correos automáticos del flujo de aprobación de procedimientos SGI."""
from __future__ import annotations

import html as html_lib
import logging
import re
from typing import Any

from app.models.sgi import SgiDocumento, SgiProcedimientoRevision, TIPO_SLUGS
from app.services.deadline_alert_email_service import normalize_validate_email
from app.services.mail_link_service import public_abs_url
from app.services.mail_service import enviar_mail, is_mail_fully_configured

log = logging.getLogger(__name__)

_EMAIL_IN_TEXT_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")


def _emails_from_text(*parts: str | None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for m in _EMAIL_IN_TEXT_RE.finditer(part or ""):
            norm = normalize_validate_email(m.group(0))
            if norm and norm not in seen:
                seen.add(norm)
                found.append(norm)
    return found


def _env_fallback(app: Any, key: str) -> list[str]:
    raw = app.config.get(key) or ""
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw]
    else:
        items = [s.strip() for s in str(raw).replace(";", ",").split(",") if s.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        norm = normalize_validate_email(item)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def resolve_revision_recipients(app: Any, rev: SgiProcedimientoRevision) -> list[str]:
    emails = _emails_from_text(rev.revisor_correo, rev.reviso)
    if not emails:
        emails = _env_fallback(app, "SGI_REVISION_MAIL_TO")
    return emails


def resolve_approval_recipients(app: Any, rev: SgiProcedimientoRevision) -> list[str]:
    emails = _emails_from_text(rev.aprobador_correo, rev.aprobo)
    if not emails:
        emails = _env_fallback(app, "SGI_APROBACION_MAIL_TO")
    return emails


def _editor_url(app: Any, doc: SgiDocumento, rev: SgiProcedimientoRevision) -> str:
    slug = TIPO_SLUGS.get(doc.tipo or "", "pg")
    return public_abs_url(app, "sgi.procedimiento_editor", slug=slug, doc_id=doc.id, rev_id=rev.id)


def _send_workflow_mail(
    app: Any,
    *,
    destinatarios: list[str],
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: str,
    context: str,
) -> bool:
    if not destinatarios:
        log.warning("SGI workflow %s: sin destinatarios de correo", context)
        return False
    if not is_mail_fully_configured(app):
        log.warning("SGI workflow %s: SMTP no configurado", context)
        return False
    try:
        enviar_mail(
            app,
            destinatarios=destinatarios,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            cuerpo_texto=cuerpo_texto,
        )
        return True
    except Exception:
        log.exception("SGI workflow %s: fallo envío de correo", context)
        return False


def workflow_mail_status_message(app: Any, *, mail_sent: bool, rol: str) -> str:
    """Mensaje honesto tras cambiar estado del flujo (revisor / aprobador)."""
    if mail_sent:
        return f"Se notificó al {rol} por correo."
    if is_mail_fully_configured(app):
        return f"No se pudo enviar el aviso por correo al {rol} (revisá los logs del servidor)."
    return (
        f"El {rol} no recibirá correo hasta configurar SMTP en el servidor "
        "(SMTP_HOST y MAIL_FROM en Render o .env)."
    )


def notify_revision_requested(app: Any, doc: SgiDocumento, rev: SgiProcedimientoRevision) -> bool:
    recipients = resolve_revision_recipients(app, rev)
    link = _editor_url(app, doc, rev)
    revisor = (rev.reviso or doc.responsable_revision or "—").strip()
    asunto = f"QDV SGI — Revisión pendiente · {doc.codigo}"
    cuerpo_html = (
        f"<p>El documento <strong>{html_lib.escape(doc.codigo)}</strong> "
        f"({html_lib.escape(doc.titulo)}) fue enviado a <strong>revisión</strong>.</p>"
        f"<p><strong>Revisor asignado:</strong> {html_lib.escape(revisor)}</p>"
        f"<p>Ingresá al sistema, revisá el contenido y confirmá con el botón "
        f"<strong>«Marcar como revisado»</strong>.</p>"
        f'<p><a href="{html_lib.escape(link)}">Abrir documento en el editor</a></p>'
    )
    cuerpo_texto = (
        f"Revisión pendiente: {doc.codigo} — {doc.titulo}\n"
        f"Revisor: {revisor}\n"
        f"Abrir: {link}"
    )
    return _send_workflow_mail(
        app,
        destinatarios=recipients,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
        context="revision_requested",
    )


def notify_pending_approval(app: Any, doc: SgiDocumento, rev: SgiProcedimientoRevision) -> bool:
    recipients = resolve_approval_recipients(app, rev)
    link = _editor_url(app, doc, rev)
    aprobador = (rev.aprobo or doc.responsable_aprobacion or "—").strip()
    revisor = (rev.reviso or "—").strip()
    asunto = f"QDV SGI — Aprobación pendiente · {doc.codigo}"
    cuerpo_html = (
        f"<p>El documento <strong>{html_lib.escape(doc.codigo)}</strong> "
        f"({html_lib.escape(doc.titulo)}) fue <strong>revisado</strong> y espera tu aprobación.</p>"
        f"<p><strong>Revisó:</strong> {html_lib.escape(revisor)}<br>"
        f"<strong>Aprobador asignado:</strong> {html_lib.escape(aprobador)}</p>"
        f"<p>Ingresá al sistema y usá el botón <strong>«Aprobar documento»</strong>.</p>"
        f'<p><a href="{html_lib.escape(link)}">Abrir documento en el editor</a></p>'
    )
    cuerpo_texto = (
        f"Aprobación pendiente: {doc.codigo} — {doc.titulo}\n"
        f"Revisó: {revisor}\nAprobador: {aprobador}\n"
        f"Abrir: {link}"
    )
    return _send_workflow_mail(
        app,
        destinatarios=recipients,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
        context="pending_approval",
    )
