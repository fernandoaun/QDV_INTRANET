"""
Avisos por correo: ventana de «unos 30 días antes» del vencimiento.

- Planificación: `PlanificacionActividad.fecha_fin` (actividades no finalizadas ni canceladas).
- Mantenimiento: `MaintenanceOrder.fecha_programada` (órdenes no finalizadas ni canceladas).

Se envía como mucho un correo por ítem (deduplicación en `DeadlineReminderSent`).
Ejecutar una vez al día: `python -m flask --app run send-deadline-reminders`.
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import DeadlineReminderSent, Equipo, MaintenanceOrder, PlanificacionActividad
from app.services.planificacion_service import actividad_display_codigo
from app.utils.datetime_operacion import now_operacion_naive_local

DOMAIN_PLANIFICACION = "planificacion"
DOMAIN_MANTENIMIENTO_ORDER = "mantenimiento_order"


@dataclass(frozen=True)
class PlanReminderItem:
    id: int
    codigo: str
    titulo: str
    fecha_fin: date


@dataclass(frozen=True)
class OrderReminderItem:
    id: int
    equipo_nombre: str
    tipo_mantenimiento: str
    fecha_programada: date
    estado: str


def _today_local() -> date:
    return now_operacion_naive_local().date()


def _days_before(app: Any | None = None) -> int:
    if app is not None:
        v = app.config.get("DEADLINE_REMINDER_DAYS_BEFORE")
        if isinstance(v, int) and v > 0:
            return max(1, min(v, 366))
    raw = (os.environ.get("DEADLINE_REMINDER_DAYS_BEFORE") or "30").strip()
    try:
        n = int(raw)
    except ValueError:
        return 30
    return max(1, min(n, 366))


def _parse_order_date(raw: str | None) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _already_sent(domain: str, entity_id: int) -> bool:
    row = db.session.execute(
        select(DeadlineReminderSent.id).where(
            DeadlineReminderSent.domain == domain,
            DeadlineReminderSent.entity_id == int(entity_id),
        )
    ).scalar_one_or_none()
    return row is not None


def _in_reminder_window(deadline: date, today: date, days_before: int) -> bool:
    start = deadline - timedelta(days=days_before)
    return start <= today <= deadline


def collect_planificacion_reminders(
    today: date | None = None,
    days_before: int | None = None,
) -> list[PlanReminderItem]:
    t = today or _today_local()
    db_days = days_before if days_before is not None else _days_before(None)
    rows = db.session.scalars(
        select(PlanificacionActividad).where(
            PlanificacionActividad.estado.notin_(("finalizada", "cancelada")),
        )
    ).all()
    out: list[PlanReminderItem] = []
    for r in rows:
        if not _in_reminder_window(r.fecha_fin, t, db_days):
            continue
        if _already_sent(DOMAIN_PLANIFICACION, r.id):
            continue
        out.append(
            PlanReminderItem(
                id=r.id,
                codigo=actividad_display_codigo(r),
                titulo=(r.titulo or "").strip() or "(sin título)",
                fecha_fin=r.fecha_fin,
            )
        )
    out.sort(key=lambda x: (x.fecha_fin, x.id))
    return out


def collect_mantenimiento_reminders(
    today: date | None = None,
    days_before: int | None = None,
) -> list[OrderReminderItem]:
    t = today or _today_local()
    db_days = days_before if days_before is not None else _days_before(None)
    rows = db.session.scalars(
        select(MaintenanceOrder)
        .options(joinedload(MaintenanceOrder.equipo))
        .where(MaintenanceOrder.estado.notin_(("finalizado", "cancelado")))
    ).all()
    out: list[OrderReminderItem] = []
    for r in rows:
        d = _parse_order_date(r.fecha_programada)
        if d is None or not _in_reminder_window(d, t, db_days):
            continue
        if _already_sent(DOMAIN_MANTENIMIENTO_ORDER, r.id):
            continue
        eq = r.equipo
        nombre = (eq.nombre_equipo if eq else "") or "—"
        out.append(
            OrderReminderItem(
                id=r.id,
                equipo_nombre=nombre.strip(),
                tipo_mantenimiento=(r.tipo_mantenimiento or "").strip() or "—",
                fecha_programada=d,
                estado=(r.estado or "").strip() or "—",
            )
        )
    out.sort(key=lambda x: (x.fecha_programada, x.id))
    return out


def _build_body(plans: list[PlanReminderItem], orders: list[OrderReminderItem], days_before: int) -> str:
    lines: list[str] = [
        f"Aviso automático — QDV Salmuera",
        f"",
        f"Ventana de aviso: desde {days_before} días antes del vencimiento hasta el día del vencimiento (fecha de operación local).",
        f"",
    ]
    if plans:
        lines.append("Planificación (fecha de fin de actividad)")
        lines.append("-" * 40)
        for p in plans:
            lines.append(f"  • [{p.codigo}] {p.titulo} — fin: {p.fecha_fin.isoformat()}")
        lines.append("")
    else:
        lines.append("(No hay actividades de planificación en ventana de aviso pendientes de notificar.)")
        lines.append("")

    if orders:
        lines.append("Mantenimiento (fecha programada de la orden)")
        lines.append("-" * 40)
        for o in orders:
            lines.append(
                f"  • Orden #{o.id} — {o.equipo_nombre} — {o.tipo_mantenimiento} — "
                f"programada: {o.fecha_programada.isoformat()} — estado: {o.estado}"
            )
        lines.append("")
    else:
        lines.append("(No hay órdenes de mantenimiento en ventana de aviso pendientes de notificar.)")
        lines.append("")

    lines.append("Este mensaje se generó sin responder.")
    return "\n".join(lines)


def _smtp_settings(app: Any) -> dict[str, Any]:
    return {
        "host": (app.config.get("SMTP_HOST") or "").strip(),
        "port": int(app.config.get("SMTP_PORT") or 587),
        "user": (app.config.get("SMTP_USER") or "").strip(),
        "password": (app.config.get("SMTP_PASSWORD") or "").strip(),
        "use_tls": bool(app.config.get("SMTP_USE_TLS", True)),
        "mail_from": (app.config.get("MAIL_FROM") or "").strip(),
        "mail_to": app.config.get("DEADLINE_ALERT_EMAIL_TO") or [],
    }


def send_smtp_email(app: Any, subject: str, body: str, recipients: list[str]) -> None:
    cfg = _smtp_settings(app)
    host = cfg["host"]
    if not host:
        raise RuntimeError("Falta SMTP_HOST en configuración.")
    mail_from = cfg["mail_from"]
    if not mail_from:
        raise RuntimeError("Falta MAIL_FROM en configuración.")
    if not recipients:
        raise RuntimeError("No hay destinatarios.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    port = cfg["port"]
    user = cfg["user"]
    password = cfg["password"]
    use_tls = cfg["use_tls"]

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=60) as smtp:
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=60) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)


def run_deadline_reminders(app: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Recolecta ítems, envía un solo correo si hay algo nuevo y registra envíos."""
    days_before = _days_before(app)
    today = _today_local()
    plans = collect_planificacion_reminders(today=today, days_before=days_before)
    orders = collect_mantenimiento_reminders(today=today, days_before=days_before)

    recipients = list(app.config.get("DEADLINE_ALERT_EMAIL_TO") or [])
    smtp_host = (app.config.get("SMTP_HOST") or "").strip()

    result: dict[str, Any] = {
        "today": today.isoformat(),
        "days_before": days_before,
        "planificacion_count": len(plans),
        "mantenimiento_count": len(orders),
        "dry_run": dry_run,
        "smtp_configured": bool(smtp_host),
        "email_sent": False,
    }

    if not plans and not orders:
        result["message"] = "Nada pendiente en ventana de aviso."
        return result

    if not recipients:
        result["message"] = "Hay ítems pero falta DEADLINE_ALERT_EMAIL_TO (lista de correos)."
        return result

    if not smtp_host:
        result["message"] = "Hay ítems pero falta SMTP_HOST (correo no enviado)."
        return result

    body = _build_body(plans, orders, days_before)
    subject = f"QDV — Avisos planificación/mantenimiento ({today.isoformat()})"

    if dry_run:
        result["message"] = "Dry-run: no se envió correo ni se guardó registro."
        result["preview_subject"] = subject
        result["preview_body"] = body
        return result

    send_smtp_email(app, subject, body, recipients)
    now = datetime.now(timezone.utc)
    for p in plans:
        db.session.add(DeadlineReminderSent(domain=DOMAIN_PLANIFICACION, entity_id=p.id, sent_at=now))
    for o in orders:
        db.session.add(DeadlineReminderSent(domain=DOMAIN_MANTENIMIENTO_ORDER, entity_id=o.id, sent_at=now))
    db.session.commit()
    result["email_sent"] = True
    result["message"] = "Correo enviado y recordatorios registrados."
    return result
