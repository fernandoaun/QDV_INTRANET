"""
Avisos automáticos del módulo Vencimientos (correo al entrar en la ventana de anticipación).

Por defecto se avisa cuando faltan hasta 30 días para el vencimiento (variable
`DEADLINE_REMINDER_DAYS_BEFORE`), una vez por registro, al correo del ítem (`email_aviso`).

Usa la misma configuración SMTP que el panel «Avisos por correo» (variables SMTP_* / MAIL_FROM).
Ejecutar una vez al día: `python -m flask --app run send-deadline-reminders`
(o el botón «Enviar avisos de vencimientos» en Administración → Avisos por correo).
"""

from __future__ import annotations

import html as html_lib
import logging
from datetime import datetime, timezone
from typing import Any

from flask import current_app

from app.extensions import db
from app.services.deadline_alert_email_service import merged_recipient_addresses, normalize_validate_email
from app.services.mail_service import enviar_mail, is_mail_fully_configured
from app.services import vencimiento_service as vs
from app.utils.datetime_operacion import now_operacion_naive_local

log = logging.getLogger(__name__)


def _public_link(app: Any, vencimiento_id: int) -> str:
    base = (app.config.get("APP_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/vencimientos/{int(vencimiento_id)}"


def _build_html_body(app: Any, v: Any) -> tuple[str, str]:
    today = now_operacion_naive_local().date()
    dias = vs.dias_restantes(v.fecha_vencimiento, today)
    sector_nombre = v.sector.nombre if getattr(v, "sector", None) else "—"
    link = _public_link(app, v.id)
    plain_lines = [
        f"Vencimiento: {v.nombre}",
        f"Sector: {sector_nombre}",
        f"Fecha de vencimiento: {v.fecha_vencimiento.isoformat()}",
        f"Días restantes: {dias}",
        f"Responsable: {v.responsable or '—'}",
        f"Observaciones: {(v.observaciones or '').strip() or '—'}",
    ]
    if link:
        plain_lines.append(f"Ver en el sistema: {link}")
    plain = "\n".join(plain_lines)

    esc = html_lib.escape
    rows = "".join(
        f"<tr><th align=\"left\">{esc(k)}</th><td>{esc(str(val))}</td></tr>"
        for k, val in (
            ("Nombre del vencimiento", v.nombre),
            ("Sector", sector_nombre),
            ("Fecha de vencimiento", v.fecha_vencimiento.isoformat()),
            ("Días restantes", str(dias)),
            ("Responsable", v.responsable or "—"),
            ("Observaciones", (v.observaciones or "").strip() or "—"),
        )
    )
    link_html = (
        f'<p><a href="{esc(link)}">Abrir en el sistema</a></p>' if link else "<p><em>Definí APP_PUBLIC_BASE_URL para incluir enlace directo.</em></p>"
    )
    html_body = (
        f"<p>Aviso automático — QDV Salmuera</p><table border=\"0\" cellpadding=\"6\">{rows}</table>"
        f"{link_html}<p style=\"color:#666;font-size:12px\">No responder a este mensaje.</p>"
    )
    return plain, html_body


def run_vencimiento_reminders(app: Any, *, dry_run: bool = False) -> dict[str, Any]:
    today = now_operacion_naive_local().date()
    days_before = vs.dias_antes_aviso_mail(app)
    rows = vs.candidatos_aviso_mail(today=today, days_before=days_before)

    cc_panel = bool(app.config.get("VENCIMIENTO_MAIL_CC_PANEL", True))
    cc_list: list[str] = merged_recipient_addresses(app) if cc_panel else []

    result: dict[str, Any] = {
        "today": today.isoformat(),
        "days_before": days_before,
        "candidates": len(rows),
        "dry_run": dry_run,
        "smtp_configured": is_mail_fully_configured(app),
        "emails_attempted": 0,
        "emails_sent": 0,
        "errors": [],
    }

    if not rows:
        result["message"] = (
            f"No hay vencimientos pendientes de aviso en la ventana de {days_before} días."
        )
        return result

    if not is_mail_fully_configured(app):
        result["message"] = (
            "Hay vencimientos en ventana pero el correo no está configurado (SMTP_HOST / MAIL_FROM). "
            "No se envió ningún aviso."
        )
        return result

    actor_sistema = "sistema/cron"

    for v in rows:
        to_addr = normalize_validate_email(v.email_aviso)
        if not to_addr:
            continue

        dias = vs.dias_restantes(v.fecha_vencimiento, today)
        if dias == 1:
            dias_txt = "1 día"
        else:
            dias_txt = f"{dias} días"
        subject = f"Aviso de vencimiento — {v.nombre} (vence en {dias_txt})"
        plain, html_body = _build_html_body(app, v)

        cc_use = [c for c in cc_list if c.lower() != to_addr.lower()]

        result["emails_attempted"] += 1
        if dry_run:
            continue

        try:
            enviar_mail(
                app,
                destinatarios=[to_addr],
                asunto=subject,
                cuerpo_html=html_body,
                cuerpo_texto=plain,
                cc=cc_use or None,
            )
            now = datetime.now(timezone.utc)
            v.aviso_30_dias_enviado = True
            v.fecha_aviso_30_dias = now
            vs.append_historial(
                v.id,
                actor_sistema,
                vs.ACCION_MAIL_ENVIADO,
                f"Asunto: {subject}. Para: {to_addr}. CC panel: {', '.join(cc_use) if cc_use else '—'}",
            )
            db.session.commit()
            result["emails_sent"] += 1
        except Exception as exc:
            db.session.rollback()
            err_txt = str(exc)[:2000]
            log.exception("Fallo SMTP aviso vencimiento id=%s", v.id)
            try:
                vs.append_historial(v.id, actor_sistema, vs.ACCION_MAIL_ERROR, f"Error SMTP: {err_txt}")
                db.session.commit()
            except Exception:
                db.session.rollback()
            result["errors"].append({"vencimiento_id": v.id, "error": err_txt})

    if dry_run:
        result["message"] = f"Dry-run: {result['emails_attempted']} correos habrían sido enviados."
        return result

    result["message"] = (
        f"Procesados {result['emails_attempted']} avisos de vencimiento; "
        f"enviados OK: {result['emails_sent']}; errores: {len(result['errors'])}."
    )
    return result
