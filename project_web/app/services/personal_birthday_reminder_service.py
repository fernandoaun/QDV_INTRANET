"""Avisos por correo: cumpleaños del día."""

from __future__ import annotations

import html as html_lib
import logging
from datetime import date
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import EmpleadoPersonal
from app.models.birthday_reminder_sent import (
    KIND_CONGRATS,
    KIND_TEAM,
    TEAM_ENTITY_ID,
    BirthdayReminderSent,
)
from app.services.mail_service import enviar_mail, is_mail_fully_configured
from app.services.personal_epp_reminder_service import resolve_empleado_email
from app.services.personal_service import cumpleanos_hoy, today_operacion

log = logging.getLogger(__name__)


def _already_sent(operacion_date: date, kind: str, empleado_id: int) -> bool:
    return (
        db.session.query(BirthdayReminderSent.id)
        .filter_by(operacion_date=operacion_date, kind=kind, empleado_id=empleado_id)
        .first()
        is not None
    )


def _claim_send_slot(operacion_date: date, kind: str, empleado_id: int) -> bool:
    """Reserva atómica en BD; True si este proceso puede enviar."""
    if _already_sent(operacion_date, kind, empleado_id):
        return False
    try:
        db.session.add(
            BirthdayReminderSent(
                operacion_date=operacion_date,
                kind=kind,
                empleado_id=empleado_id,
            )
        )
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def _release_send_slot(operacion_date: date, kind: str, empleado_id: int) -> None:
    db.session.query(BirthdayReminderSent).filter_by(
        operacion_date=operacion_date,
        kind=kind,
        empleado_id=empleado_id,
    ).delete()
    db.session.commit()


def _empleados_activos_con_email() -> list[tuple[EmpleadoPersonal, str]]:
    from app.services.personal_service import _query_empleados_con_legajo

    rows = (
        _query_empleados_con_legajo()
        .filter(EmpleadoPersonal.estado == "activo")
        .order_by(EmpleadoPersonal.apellido, EmpleadoPersonal.nombre)
        .all()
    )
    out: list[tuple[EmpleadoPersonal, str]] = []
    seen: set[str] = set()
    for emp in rows:
        addr = resolve_empleado_email(emp)
        if not addr or addr in seen:
            continue
        seen.add(addr)
        out.append((emp, addr))
    return out


def _build_congrats_bodies(empleado: EmpleadoPersonal) -> tuple[str, str, str]:
    nombre = empleado.nombre_completo
    esc = html_lib.escape
    asunto = "QDV — ¡Feliz cumpleaños!"
    plain = (
        f"Hola {nombre},\n\n"
        "¡Feliz cumpleaños! Todo el equipo de Química del Valle te desea un excelente día.\n\n"
        "Saludos cordiales."
    )
    html_body = (
        f"<p>Hola <strong>{esc(nombre)}</strong>,</p>"
        "<p>¡Feliz cumpleaños! Todo el equipo de <strong>Química del Valle</strong> te desea un excelente día.</p>"
        '<p style="color:#666;font-size:12px">No responder a este mensaje.</p>'
    )
    return asunto, plain, html_body


def _build_team_bodies(festejados: list[EmpleadoPersonal]) -> tuple[str, str, str]:
    esc = html_lib.escape
    nombres = [e.nombre_completo for e in festejados]
    if len(nombres) == 1:
        asunto = f"QDV — Hoy es el cumpleaños de {nombres[0]}"
        intro = f"Hoy {nombres[0]} festeja su cumpleaños."
    else:
        asunto = f"QDV — Cumpleaños de hoy ({len(nombres)})"
        intro = "Hoy festejan su cumpleaños:"
    plain = "Hola,\n\n" + intro + "\n"
    if len(nombres) > 1:
        plain += "\n".join(f"- {n}" for n in nombres)
    plain += "\n\n¡Saludemos y felicitemos a quienes cumplen años hoy!\n"
    if len(nombres) == 1:
        html_items = f"<p>{esc(intro)}</p>"
    else:
        items = "".join(f"<li>{esc(n)}</li>" for n in nombres)
        html_items = f"<p>{esc(intro)}</p><ul>{items}</ul>"
    html_body = (
        "<p>Hola,</p>"
        f"{html_items}"
        "<p>¡Saludemos y felicitemos a quienes cumplen años hoy!</p>"
        '<p style="color:#666;font-size:12px">No responder a este mensaje.</p>'
    )
    return asunto, plain, html_body


def _send_congrats(app: Any, empleado: EmpleadoPersonal, *, dry_run: bool) -> tuple[bool, str]:
    hoy = today_operacion()
    empleado_id = int(empleado.id)
    if _already_sent(hoy, KIND_CONGRATS, empleado_id):
        return True, "Ya enviado hoy."
    to_addr = resolve_empleado_email(empleado)
    if not to_addr:
        return False, f"Sin email válido en legajo de {empleado.nombre_completo}."
    if dry_run:
        return True, f"Dry-run: felicitación a {to_addr}."
    if not _claim_send_slot(hoy, KIND_CONGRATS, empleado_id):
        return True, "Ya enviado hoy."
    asunto, plain, html_body = _build_congrats_bodies(empleado)
    try:
        enviar_mail(
            app,
            destinatarios=[to_addr],
            asunto=asunto,
            cuerpo_html=html_body,
            cuerpo_texto=plain,
        )
    except Exception as exc:
        _release_send_slot(hoy, KIND_CONGRATS, empleado_id)
        log.exception("Fallo envío cumpleaños empleado_id=%s", empleado.id)
        return False, f"Error SMTP: {exc}"
    return True, f"Felicitación enviada a {to_addr}."


def _send_team_announcement(
    app: Any,
    festejados: list[EmpleadoPersonal],
    *,
    dry_run: bool,
) -> tuple[int, list[str]]:
    hoy = today_operacion()
    if _already_sent(hoy, KIND_TEAM, TEAM_ENTITY_ID):
        return 0, []
    recipients = _empleados_activos_con_email()
    if not recipients:
        return 0, ["No hay destinatarios con email válido para aviso grupal."]
    asunto, plain, html_body = _build_team_bodies(festejados)
    sent = 0
    errors: list[str] = []
    if dry_run:
        return len(recipients), errors
    if not _claim_send_slot(hoy, KIND_TEAM, TEAM_ENTITY_ID):
        return 0, []
    for emp, addr in recipients:
        try:
            enviar_mail(
                app,
                destinatarios=[addr],
                asunto=asunto,
                cuerpo_html=html_body,
                cuerpo_texto=plain,
            )
            sent += 1
        except Exception as exc:
            log.exception("Fallo aviso grupal cumpleaños a %s", addr)
            errors.append(f"{emp.nombre_completo} ({addr}): {exc}")
    if not sent:
        _release_send_slot(hoy, KIND_TEAM, TEAM_ENTITY_ID)
    return sent, errors


def run_birthday_reminders(app: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Envía felicitaciones y aviso grupal por cada cumpleaños del día."""
    hoy = today_operacion()
    festejados = cumpleanos_hoy()
    result: dict[str, Any] = {
        "today": hoy.isoformat(),
        "cumpleaneros": len(festejados),
        "congrats_attempted": 0,
        "congrats_sent": 0,
        "team_emails_sent": 0,
        "dry_run": dry_run,
        "smtp_configured": is_mail_fully_configured(app),
        "errors": [],
    }

    if not festejados:
        result["message"] = "Hoy no hay cumpleaños de empleados activos."
        return result

    if not is_mail_fully_configured(app):
        result["message"] = (
            f"Hay {len(festejados)} cumpleaño(s) hoy pero SMTP no está configurado."
        )
        return result

    for emp in festejados:
        result["congrats_attempted"] += 1
        if dry_run:
            addr = resolve_empleado_email(emp)
            if addr and not _already_sent(hoy, KIND_CONGRATS, int(emp.id)):
                result["congrats_sent"] += 1
            elif not addr:
                result["errors"].append(f"{emp.nombre_completo}: sin email válido.")
            continue
        ok, detail = _send_congrats(app, emp, dry_run=False)
        if ok and "Felicitación enviada" in detail:
            result["congrats_sent"] += 1
        elif not ok:
            result["errors"].append(f"{emp.nombre_completo}: {detail}")

    team_sent, team_errors = _send_team_announcement(app, festejados, dry_run=dry_run)
    result["team_emails_sent"] = team_sent
    result["errors"].extend(team_errors)

    nombres = ", ".join(e.nombre_completo for e in festejados)
    if dry_run:
        result["message"] = f"Dry-run: cumpleaños de hoy — {nombres}."
    elif result["congrats_sent"] or result["team_emails_sent"]:
        result["message"] = (
            f"Avisos de cumpleaños enviados ({nombres}): "
            f"{result['congrats_sent']} felicitación(es), {result['team_emails_sent']} aviso(s) al equipo."
        )
    else:
        result["message"] = f"No se pudo enviar avisos de cumpleaños ({nombres})."
    return result
