"""Avisos por correo: cumpleaños del día."""

from __future__ import annotations

import html as html_lib
import logging
from pathlib import Path
from typing import Any

from app.extensions import db
from app.models import EmpleadoPersonal
from app.services.mail_service import enviar_mail, is_mail_fully_configured
from app.services.personal_epp_reminder_service import resolve_empleado_email
from app.services.personal_service import cumpleanos_hoy, today_operacion

log = logging.getLogger(__name__)


def _team_mail_lock_path(app: Any, iso_date: str) -> Path:
    p = Path(app.instance_path) / "locks"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"birthday_team_mail_{iso_date}.lock"


def _team_mail_already_sent(app: Any, iso_date: str) -> bool:
    return _team_mail_lock_path(app, iso_date).exists()


def _mark_team_mail_sent(app: Any, iso_date: str) -> None:
    _team_mail_lock_path(app, iso_date).touch()


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
    if empleado.aviso_cumpleanos_anio == hoy.year:
        return True, "Ya enviado este año."
    to_addr = resolve_empleado_email(empleado)
    if not to_addr:
        return False, f"Sin email válido en legajo de {empleado.nombre_completo}."
    if dry_run:
        return True, f"Dry-run: felicitación a {to_addr}."
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
        log.exception("Fallo envío cumpleaños empleado_id=%s", empleado.id)
        return False, f"Error SMTP: {exc}"
    empleado.aviso_cumpleanos_anio = hoy.year
    db.session.commit()
    return True, f"Felicitación enviada a {to_addr}."


def _send_team_announcement(
    app: Any,
    festejados: list[EmpleadoPersonal],
    *,
    dry_run: bool,
) -> tuple[int, list[str]]:
    iso = today_operacion().isoformat()
    if _team_mail_already_sent(app, iso):
        return 0, []
    recipients = _empleados_activos_con_email()
    if not recipients:
        return 0, ["No hay destinatarios con email válido para aviso grupal."]
    asunto, plain, html_body = _build_team_bodies(festejados)
    sent = 0
    errors: list[str] = []
    if dry_run:
        return len(recipients), errors
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
    if sent:
        _mark_team_mail_sent(app, iso)
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
            if addr and emp.aviso_cumpleanos_anio != hoy.year:
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
