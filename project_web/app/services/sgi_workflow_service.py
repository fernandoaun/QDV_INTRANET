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


def _emails_from_puesto(puesto_id: str | None) -> list[str]:
    nid = (puesto_id or "").strip()
    if not nid:
        return []
    try:
        from app.services.sgi_anexo_service import organigrama_emails_for_puesto

        return list(organigrama_emails_for_puesto(nid))
    except Exception:
        log.exception("SGI workflow: no se pudieron resolver emails del puesto %s", nid)
        return []


def resolve_revision_recipients(app: Any, rev: SgiProcedimientoRevision) -> list[str]:
    from app.services.sgi_procedimiento_service import get_revision_puesto_ids

    emails = _emails_from_puesto(get_revision_puesto_ids(rev).get("reviso_puesto_id"))
    if not emails:
        emails = _emails_from_text(rev.revisor_correo, rev.reviso)
    if not emails:
        emails = _env_fallback(app, "SGI_REVISION_MAIL_TO")
    return emails


def resolve_approval_recipients(app: Any, rev: SgiProcedimientoRevision) -> list[str]:
    from app.services.sgi_procedimiento_service import get_revision_puesto_ids

    emails = _emails_from_puesto(get_revision_puesto_ids(rev).get("aprobo_puesto_id"))
    if not emails:
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


def workflow_mail_status_message(app: Any, *, mail_sent: bool, rol: str, destinatarios: list[str] | None = None) -> str:
    """Mensaje honesto tras cambiar estado del flujo (revisor / aprobador): por correo y, si tiene celular, por WhatsApp."""
    if mail_sent:
        if destinatarios is None:
            return f"Se notificó al {rol} por correo."
        from app.services.whatsapp_avisos_service import telefonos_por_email

        con_celular = telefonos_por_email(destinatarios)
        sin_celular = [e for e in destinatarios if e.strip().lower() not in con_celular]
        if not sin_celular:
            return f"Se notificó al {rol} por correo y por WhatsApp."
        quienes = ", ".join(sin_celular)
        if con_celular:
            return f"Se notificó al {rol} por correo y por WhatsApp (a {quienes} solo por correo: no está en ningún legajo con celular)."
        return f"Se notificó al {rol} por correo; por WhatsApp no, porque {quienes} no está en ningún legajo con celular."
    if is_mail_fully_configured(app):
        return f"No se pudo enviar el aviso por correo al {rol} (revisá los logs del servidor)."
    return (
        f"El {rol} no recibirá correo hasta configurar SMTP en el servidor "
        "(SMTP_HOST y MAIL_FROM en Render o .env)."
    )


def _pdf(doc: SgiDocumento, rev: SgiProcedimientoRevision) -> tuple[str, bytes, str] | None:
    from app.services.sgi_pdf_service import adjunto_difusion

    return adjunto_difusion(doc, rev)


def _send_personal(
    app: Any,
    doc: SgiDocumento,
    rev: SgiProcedimientoRevision,
    *,
    recipients: list[str],
    tipo_accion: str,
    asunto: str,
    intro_html: str,
    intro_texto: str,
    boton: str,
    context: str,
    texto_whatsapp: str = "",
) -> bool:
    """Un mail por destinatario con su link de acción (sin entrar al sistema) y el documento en PDF."""
    from app.services import accion_link_service as accion_svc

    if not recipients:
        log.warning("SGI workflow %s: sin destinatarios de correo", context)
        return False
    adjunto = _pdf(doc, rev)
    editor = _editor_url(app, doc, rev)
    algun = False
    for dest in recipients:
        link = accion_svc.url(app, tipo_accion, rev.id, email=dest)
        cuerpo_html = (
            intro_html
            + ("<p>Te mandamos el documento adjunto en PDF.</p>" if adjunto else "")
            + f'<p><a href="{html_lib.escape(link)}"><strong>{html_lib.escape(boton)}</strong></a> '
            "(desde el celular, sin entrar al sistema)</p>"
            + f'<p style="color:#666;font-size:12px">También podés abrirlo en el editor: '
            f'<a href="{html_lib.escape(editor)}">{html_lib.escape(editor)}</a></p>'
        )
        cuerpo_texto = (
            intro_texto
            + ("\nTe mandamos el documento adjunto en PDF." if adjunto else "")
            + f"\n\n{boton}: {link}"
        )
        try:
            if not is_mail_fully_configured(app):
                log.warning("SGI workflow %s: SMTP no configurado", context)
                return False
            enviar_mail(
                app,
                destinatarios=[dest],
                asunto=asunto,
                cuerpo_html=cuerpo_html,
                cuerpo_texto=cuerpo_texto,
                adjuntos=[adjunto] if adjunto else None,
                texto_whatsapp=texto_whatsapp or None,
            )
            algun = True
        except Exception:
            log.exception("SGI workflow %s: fallo envío de correo a %s", context, dest)
    return algun


def notify_revision_requested(app: Any, doc: SgiDocumento, rev: SgiProcedimientoRevision) -> bool:
    from app.services.accion_link_service import SGI_REVISAR

    revisor = (rev.reviso or doc.responsable_revision or "—").strip()
    esc = html_lib.escape
    return _send_personal(
        app,
        doc,
        rev,
        recipients=resolve_revision_recipients(app, rev),
        tipo_accion=SGI_REVISAR,
        asunto=f"QDV SGI — Revisión pendiente · {doc.codigo}",
        intro_html=(
            f"<p>El documento <strong>{esc(doc.codigo)}</strong> ({esc(doc.titulo)}) fue enviado a "
            f"<strong>revisión</strong>.</p><p><strong>Revisor asignado:</strong> {esc(revisor)}</p>"
            "<p>Leelo y, desde el link, marcalo como revisado o devolvelo con observaciones.</p>"
        ),
        intro_texto=(
            f"Revisión pendiente: {doc.codigo} — {doc.titulo}\nRevisor: {revisor}\n"
            "Leelo y, desde el link, marcalo como revisado o devolvelo con observaciones."
        ),
        boton="Revisar",
        context="revision_requested",
        texto_whatsapp=(
            f"{doc.codigo} — {doc.titulo} ({rev.revision_label}) fue enviado a revisión y te toca revisarlo. "
            "Te mando el PDF.\n\nCuando lo leas, respondeme *REVISADO*, o *DEVOLVER* y qué hay que corregir."
        ),
    )


def notify_pending_approval(app: Any, doc: SgiDocumento, rev: SgiProcedimientoRevision) -> bool:
    from app.services.accion_link_service import SGI_APROBAR

    aprobador = (rev.aprobo or doc.responsable_aprobacion or "—").strip()
    revisor = (rev.reviso or "—").strip()
    esc = html_lib.escape
    return _send_personal(
        app,
        doc,
        rev,
        recipients=resolve_approval_recipients(app, rev),
        tipo_accion=SGI_APROBAR,
        asunto=f"QDV SGI — Aprobación pendiente · {doc.codigo}",
        intro_html=(
            f"<p>El documento <strong>{esc(doc.codigo)}</strong> ({esc(doc.titulo)}) fue <strong>revisado</strong> "
            f"y espera tu aprobación.</p><p><strong>Revisó:</strong> {esc(revisor)}<br>"
            f"<strong>Aprobador asignado:</strong> {esc(aprobador)}</p>"
            "<p>Leelo y, desde el link, aprobalo o devolvelo con observaciones.</p>"
        ),
        intro_texto=(
            f"Aprobación pendiente: {doc.codigo} — {doc.titulo}\nRevisó: {revisor}\nAprobador: {aprobador}\n"
            "Leelo y, desde el link, aprobalo o devolvelo con observaciones."
        ),
        boton="Aprobar",
        context="pending_approval",
        texto_whatsapp=(
            f"{doc.codigo} — {doc.titulo} ({rev.revision_label}) fue revisado por {revisor} y espera tu aprobación. "
            "Te mando el PDF.\n\nCuando lo leas, respondeme *APROBAR*, o *DEVOLVER* y qué hay que corregir."
        ),
    )


def notify_devuelto(app: Any, doc: SgiDocumento, rev: SgiProcedimientoRevision, actor_label: str, observaciones: str) -> bool:
    """Aviso a quien elaboró: el documento volvió a borrador con observaciones."""
    from app.services.sgi_procedimiento_service import emails_elaborador

    recipients = emails_elaborador(rev) or _env_fallback(app, "SGI_REVISION_MAIL_TO")
    link = _editor_url(app, doc, rev)
    esc = html_lib.escape
    return _send_workflow_mail(
        app,
        destinatarios=recipients,
        asunto=f"QDV SGI — Documento devuelto con observaciones · {doc.codigo}",
        cuerpo_html=(
            f"<p><strong>{esc(actor_label)}</strong> devolvió el documento <strong>{esc(doc.codigo)}</strong> "
            f"({esc(doc.titulo)}) a borrador.</p><p><strong>Observaciones:</strong><br>{esc(observaciones)}</p>"
            "<p>Corregilo y volvé a enviarlo a revisión.</p>"
            f'<p><a href="{esc(link)}">Abrir documento en el editor</a></p>'
        ),
        cuerpo_texto=(
            f"{actor_label} devolvió {doc.codigo} — {doc.titulo} a borrador.\n"
            f"Observaciones: {observaciones}\n\nCorregilo y volvé a enviarlo a revisión.\nEditor: {link}"
        ),
        context="devuelto",
    )
