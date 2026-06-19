"""Avisos por correo del workflow de vacaciones."""

from __future__ import annotations

import html as html_lib
import logging
from datetime import datetime, timezone
from typing import Any

from flask import url_for

from app.extensions import db
from app.models import PersonalVacacion, User
from app.services.mail_service import enviar_mail, is_mail_fully_configured
from app.services.personal_epp_reminder_service import resolve_empleado_email
from app.services import personal_service as ps

log = logging.getLogger(__name__)


def _abs_url(app: Any, endpoint: str, **values: Any) -> str:
    base = (app.config.get("APP_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if base:
        path = url_for(endpoint, **values)
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"
    try:
        with app.app_context():
            return url_for(endpoint, _external=True, **values)
    except RuntimeError:
        return url_for(endpoint, **values)


def resolve_responsable_email(app: Any) -> str | None:
    cfg = ps.get_vacacion_config()
    if cfg.responsable_user_id is None:
        return None
    user = db.session.get(User, int(cfg.responsable_user_id))
    if user is None or not user.activo:
        return None
    emp = ps.get_empleado_by_user_id(user.id)
    return resolve_empleado_email(emp)


def _format_rango(vac: PersonalVacacion) -> str:
    return f"{vac.fecha_desde.strftime('%d/%m/%Y')} — {vac.fecha_hasta.strftime('%d/%m/%Y')} ({vac.dias} días)"


def notify_solicitud_vacacion(app: Any, vac: PersonalVacacion) -> tuple[bool, str]:
    if (vac.estado or "").strip() != "solicitada":
        return True, ""
    to_addr = resolve_responsable_email(app)
    if not to_addr:
        return False, "No hay responsable de vacaciones con email válido configurado."
    if not is_mail_fully_configured(app):
        return False, "SMTP no configurado."

    emp = vac.empleado
    nombre = emp.nombre_completo if emp else "—"
    link = _abs_url(app, "personal.vacaciones")
    esc = html_lib.escape
    rango = _format_rango(vac)
    obs = (vac.observaciones or "").strip()

    asunto = f"QDV — Solicitud de vacaciones: {nombre}"
    plain = (
        f"Nueva solicitud de vacaciones de {nombre}.\n\n"
        f"Período {vac.anio}: {rango}\n"
    )
    if obs:
        plain += f"Observaciones del empleado: {obs}\n"
    plain += f"\nGestionar en el sistema: {link}\n"

    html_body = (
        f"<p>Nueva solicitud de vacaciones de <strong>{esc(nombre)}</strong>.</p>"
        f"<p><strong>Período {vac.anio}:</strong> {esc(rango)}</p>"
    )
    if obs:
        html_body += f"<p><strong>Observaciones:</strong> {esc(obs)}</p>"
    html_body += f'<p><a href="{esc(link)}">Gestionar solicitudes</a></p>'

    try:
        enviar_mail(app, destinatarios=[to_addr], asunto=asunto, cuerpo_html=html_body, cuerpo_texto=plain)
    except Exception as exc:
        log.exception("Fallo mail solicitud vacaciones id=%s", vac.id)
        return False, f"Error SMTP: {exc}"

    vac.solicitud_aviso_at = datetime.now(timezone.utc)
    db.session.commit()
    return True, f"Aviso enviado al responsable ({to_addr})."


def notify_empleado_vacacion_gestionada(app: Any, vac: PersonalVacacion) -> tuple[bool, str]:
    emp = vac.empleado
    to_addr = resolve_empleado_email(emp)
    if not to_addr:
        return False, "El empleado no tiene email válido en su legajo."
    if not is_mail_fully_configured(app):
        return False, "SMTP no configurado."

    estado = (vac.estado or "").strip()
    link = _abs_url(app, "personal.mis_vacaciones")
    esc = html_lib.escape
    nombre = emp.nombre_completo if emp else "—"
    motivo = (vac.motivo_responsable or "").strip()

    if estado == "aprobada":
        asunto = "QDV — Vacaciones aprobadas"
        intro = f"Tu solicitud de vacaciones fue aprobada: {_format_rango(vac)}."
    elif estado == "modificada":
        asunto = "QDV — Propuesta de modificación de vacaciones"
        orig = ""
        if vac.fecha_desde_original and vac.fecha_hasta_original:
            orig = (
                f" Pediste {vac.fecha_desde_original.strftime('%d/%m/%Y')} — "
                f"{vac.fecha_hasta_original.strftime('%d/%m/%Y')}."
            )
        intro = f"El responsable propuso nuevas fechas: {_format_rango(vac)}.{orig} Confirmá en el sistema."
    elif estado == "rechazada":
        asunto = "QDV — Vacaciones rechazadas"
        intro = f"Tu solicitud de vacaciones fue rechazada.{f' Motivo: {motivo}.' if motivo else ''} Confirmá en el sistema."
    else:
        return True, ""

    plain = f"Hola {nombre},\n\n{intro}\n\nVer en el sistema: {link}\n"
    html_body = (
        f"<p>Hola <strong>{esc(nombre)}</strong>,</p>"
        f"<p>{esc(intro)}</p>"
        f'<p><a href="{esc(link)}">Mis vacaciones</a></p>'
    )

    try:
        enviar_mail(app, destinatarios=[to_addr], asunto=asunto, cuerpo_html=html_body, cuerpo_texto=plain)
    except Exception as exc:
        log.exception("Fallo mail gestión vacaciones id=%s", vac.id)
        return False, f"Error SMTP: {exc}"
    return True, f"Aviso enviado a {to_addr}."


def maybe_notify_solicitud_vacacion(vac: PersonalVacacion) -> tuple[bool, str]:
    try:
        from flask import current_app

        app = current_app._get_current_object()
    except RuntimeError:
        return True, ""
    return notify_solicitud_vacacion(app, vac)


def maybe_notify_empleado_vacacion_gestionada(vac: PersonalVacacion) -> tuple[bool, str]:
    try:
        from flask import current_app

        app = current_app._get_current_object()
    except RuntimeError:
        return True, ""
    return notify_empleado_vacacion_gestionada(app, vac)
