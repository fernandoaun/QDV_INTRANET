"""Correos de difusión SGI: procedimientos/manuales aplicables a un perfil o usuario."""
from __future__ import annotations

import html as html_lib
import logging
from typing import Any

from flask import has_app_context
from sqlalchemy import select

from app.extensions import db
from app.models.sgi import (
    ESTADO_APROBADO,
    ESTADO_VIGENTE,
    SgiDocumento,
    SgiProcedimientoRevision,
    TIPO_LABELS,
    TIPO_SLUGS,
)
from app.models.user import User
from app.services.deadline_alert_email_service import normalize_validate_email
from app.services.mail_link_service import public_abs_url
from app.services.mail_service import enviar_mail, is_mail_fully_configured
from app.services.personal_epp_reminder_service import resolve_empleado_email
from app.services.sgi_documento_perfil_service import (
    user_alcanzado_por_documento,
    users_with_perfiles,
)
from app.user_roles import ROLE_LABORATORISTA, normalize_stored_rol

log = logging.getLogger(__name__)


def _user_emails(user: User) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()
    emp = getattr(user, "empleado_personal", None)
    if emp is None:
        from app.models import EmpleadoPersonal

        emp = db.session.scalar(
            select(EmpleadoPersonal).where(EmpleadoPersonal.user_id == int(user.id)).limit(1)
        )
    addr = resolve_empleado_email(emp)
    if addr and addr.lower() not in seen:
        seen.add(addr.lower())
        emails.append(addr)
    uname = (user.username or "").strip()
    if "@" in uname:
        norm = normalize_validate_email(uname)
        if norm and norm.lower() not in seen:
            seen.add(norm.lower())
            emails.append(norm)
    return emails


def coverage_doc_ids(user_id: int) -> frozenset[int]:
    """Ids de documentos aprobados/vigentes que alcanzan al usuario (sin atajo admin)."""
    user = db.session.get(User, int(user_id))
    if user is None or not user.activo:
        return frozenset()
    return frozenset(int(doc.id) for doc, _rev in documentos_vigentes_para_usuario(user))


def documentos_vigentes_para_usuario(user: User) -> list[tuple[SgiDocumento, SgiProcedimientoRevision]]:
    from app.services import sgi_procedimiento_service as proc_svc

    if user is None or not user.activo:
        return []
    if user.is_admin:
        return []
    if normalize_stored_rol(user.rol) == ROLE_LABORATORISTA:
        return []

    rows = (
        db.session.query(SgiDocumento)
        .filter(
            SgiDocumento.deleted_at.is_(None),
            SgiDocumento.es_procedimiento_visual.is_(True),
            SgiDocumento.estado.in_((ESTADO_APROBADO, ESTADO_VIGENTE)),
        )
        .order_by(SgiDocumento.codigo, SgiDocumento.id)
        .all()
    )
    out: list[tuple[SgiDocumento, SgiProcedimientoRevision]] = []
    for doc in rows:
        if not user_alcanzado_por_documento(user, int(doc.id)):
            continue
        rev = proc_svc.revision_vigente_aprobada(doc)
        if rev is None:
            continue
        out.append((doc, rev))
    return out


def _vista_url(app: Any, doc: SgiDocumento, rev: SgiProcedimientoRevision) -> str:
    slug = TIPO_SLUGS.get(doc.tipo or "", "pg")
    return public_abs_url(app, "sgi.procedimiento_vista", slug=slug, doc_id=doc.id, rev_id=rev.id)


def _doc_tipo_label(doc: SgiDocumento) -> str:
    return TIPO_LABELS.get(doc.tipo or "", doc.tipo or "Documento")


def _send_mail(
    app: Any,
    *,
    destinatarios: list[str],
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: str,
    context: str,
) -> bool:
    if not destinatarios:
        log.warning("SGI difusión %s: sin destinatarios", context)
        return False
    if not is_mail_fully_configured(app):
        log.warning("SGI difusión %s: SMTP no configurado", context)
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
        log.exception("SGI difusión %s: fallo envío", context)
        return False


def _build_digest_bodies(
    app: Any,
    items: list[tuple[SgiDocumento, SgiProcedimientoRevision]],
    *,
    intro_html: str,
    intro_texto: str,
) -> tuple[str, str]:
    lis: list[str] = []
    lines: list[str] = [intro_texto, ""]
    for doc, rev in items:
        link = _vista_url(app, doc, rev)
        tipo = _doc_tipo_label(doc)
        codigo = html_lib.escape(doc.codigo or "")
        titulo = html_lib.escape(doc.titulo or "")
        tipo_e = html_lib.escape(tipo)
        rev_l = html_lib.escape(rev.revision_label or "")
        lis.append(
            f"<li><strong>{codigo}</strong> — {titulo}"
            f" <span>({tipo_e}, {rev_l})</span><br>"
            f'<a href="{html_lib.escape(link)}">Abrir documento</a></li>'
        )
        lines.append(f"- {doc.codigo} — {doc.titulo} ({tipo}, {rev.revision_label})")
        lines.append(f"  {link}")
        lines.append("")
    cuerpo_html = f"<p>{intro_html}</p><ul>{''.join(lis)}</ul>"
    cuerpo_texto = "\n".join(lines).strip()
    return cuerpo_html, cuerpo_texto


def send_digest_to_user(
    app: Any,
    user: User,
    items: list[tuple[SgiDocumento, SgiProcedimientoRevision]] | None = None,
    *,
    motivo: str = "cobertura",
) -> bool:
    """Envía la lista de procedimientos/manuales aplicables con links de lectura."""
    if items is None:
        items = documentos_vigentes_para_usuario(user)
    if not items:
        return False
    dest = _user_emails(user)
    if not dest:
        log.warning(
            "SGI difusión %s: usuario %s sin email (legajo/username)",
            motivo,
            getattr(user, "username", user.id),
        )
        return False
    nombre = html_lib.escape((user.nombre_completo or user.username or "usuario").strip())
    intro_html = (
        f"Hola {nombre}, según tu puesto/perfil en el organigrama te corresponden "
        f"los siguientes documentos vigentes del Sistema de Gestión de la Calidad. "
        f"Ingresá a cada enlace para leerlos:"
    )
    intro_texto = (
        f"Hola {(user.nombre_completo or user.username or 'usuario').strip()}, "
        f"documentos SGI vigentes que te aplican:"
    )
    cuerpo_html, cuerpo_texto = _build_digest_bodies(
        app, items, intro_html=intro_html, intro_texto=intro_texto
    )
    n = len(items)
    asunto = f"QDV SGI — Documentos vigentes que te aplican ({n})"
    return _send_mail(
        app,
        destinatarios=dest,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
        context=f"digest_{motivo}_u{user.id}",
    )


def notify_usuario_si_cobertura_aumenta(
    app: Any | None,
    user_id: int,
    before_doc_ids: frozenset[int] | set[int] | None,
) -> bool:
    """Si el usuario pasó a alcanzar documentos nuevos, manda el digest completo."""
    if app is None:
        if not has_app_context():
            return False
        from flask import current_app

        app = current_app._get_current_object()
    user = db.session.get(User, int(user_id))
    if user is None or not user.activo:
        return False
    items = documentos_vigentes_para_usuario(user)
    after_ids = frozenset(int(d.id) for d, _ in items)
    before = frozenset(int(x) for x in (before_doc_ids or ()))
    if not (after_ids - before):
        return False
    return send_digest_to_user(app, user, items, motivo="alta_cobertura")


def notify_usuarios_por_nuevos_perfiles(
    app: Any | None,
    doc: SgiDocumento,
    nuevos_perfiles: list[str],
) -> int:
    """Al agregar puestos/perfiles a un doc ya aprobado: digest a los usuarios alcanzados."""
    if not nuevos_perfiles:
        return 0
    if doc.estado not in (ESTADO_APROBADO, ESTADO_VIGENTE):
        return 0
    if app is None:
        if not has_app_context():
            return 0
        from flask import current_app

        app = current_app._get_current_object()
    users = users_with_perfiles(nuevos_perfiles)
    sent = 0
    for u in users:
        if send_digest_to_user(app, u, motivo=f"perfil_doc_{doc.id}"):
            sent += 1
    return sent


def notify_approval_emails(
    app: Any | None,
    doc: SgiDocumento,
    rev: SgiProcedimientoRevision,
) -> int:
    """Al aprobar: mail con link del documento a cada usuario del perfil (además de la campana)."""
    if app is None:
        if not has_app_context():
            return 0
        from flask import current_app

        app = current_app._get_current_object()
    from app.services.sgi_notification_service import users_to_notify_document_approved

    users = users_to_notify_document_approved(doc, rev)
    link = _vista_url(app, doc, rev)
    tipo = _doc_tipo_label(doc)
    sent = 0
    for u in users:
        dest = _user_emails(u)
        if not dest:
            continue
        nombre = html_lib.escape((u.nombre_completo or u.username or "").strip() or "usuario")
        codigo = html_lib.escape(doc.codigo or "")
        titulo = html_lib.escape(doc.titulo or "")
        tipo_e = html_lib.escape(tipo)
        rev_l = html_lib.escape(rev.revision_label or "")
        asunto = f"QDV SGI — Documento aprobado · {doc.codigo}"
        cuerpo_html = (
            f"<p>Hola {nombre}, se aprobó un documento que aplica a tu puesto/perfil:</p>"
            f"<p><strong>{codigo}</strong> — {titulo}<br>"
            f"{tipo_e} · {rev_l}</p>"
            f'<p><a href="{html_lib.escape(link)}">Abrir documento</a></p>'
        )
        cuerpo_texto = (
            f"Documento aprobado que te aplica: {doc.codigo} — {doc.titulo}\n"
            f"{tipo} · {rev.revision_label}\n"
            f"Abrir: {link}"
        )
        if _send_mail(
            app,
            destinatarios=dest,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            cuerpo_texto=cuerpo_texto,
            context=f"aprobacion_doc_{doc.id}_u{u.id}",
        ):
            sent += 1
    return sent


def notify_usuarios_cobertura_batch(
    app: Any | None,
    snapshots: dict[int, frozenset[int]],
) -> int:
    """Para varios usuarios: `user_id -> coverage_doc_ids` previos al cambio."""
    if not snapshots:
        return 0
    if app is None:
        if not has_app_context():
            return 0
        from flask import current_app

        app = current_app._get_current_object()
    sent = 0
    for uid, before in snapshots.items():
        if notify_usuario_si_cobertura_aumenta(app, int(uid), before):
            sent += 1
    return sent
