"""
Envío SMTP centralizado (lee siempre la misma configuración que el resto del sistema).

Variables de entorno / app.config: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
SMTP_USE_TLS, MAIL_FROM — mismas que usa `deadline_reminder_service` y el panel de avisos.
"""

from __future__ import annotations

import html as html_lib
import smtplib
from email.message import EmailMessage
from typing import Any


def smtp_settings_from_app(app: Any) -> dict[str, Any]:
    return {
        "host": (app.config.get("SMTP_HOST") or "").strip(),
        "port": int(app.config.get("SMTP_PORT") or 587),
        "user": (app.config.get("SMTP_USER") or "").strip(),
        "password": (app.config.get("SMTP_PASSWORD") or "").strip(),
        "use_tls": bool(app.config.get("SMTP_USE_TLS", True)),
        "mail_from": (app.config.get("MAIL_FROM") or "").strip(),
    }


def is_mail_fully_configured(app: Any) -> bool:
    cfg = smtp_settings_from_app(app)
    return bool(cfg["host"] and cfg["mail_from"])


def _dedupe_emails(addresses: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in addresses:
        e = (raw or "").strip().lower()
        if not e or e in seen:
            continue
        seen.add(e)
        out.append((raw or "").strip())
    return out


def enviar_mail(
    app: Any,
    *,
    destinatarios: list[str],
    asunto: str,
    cuerpo_html: str | None = None,
    cuerpo_texto: str | None = None,
    cc: list[str] | None = None,
) -> None:
    """
    Envía un correo usando la configuración SMTP del sistema.

    Debe indicarse `cuerpo_html` y/o `cuerpo_texto`. Si solo hay HTML, se genera texto plano simple.
    """
    cfg = smtp_settings_from_app(app)
    host = cfg["host"]
    mail_from = cfg["mail_from"]
    if not host:
        raise RuntimeError("Falta SMTP_HOST en configuración.")
    if not mail_from:
        raise RuntimeError("Falta MAIL_FROM en configuración.")

    to_norm = _dedupe_emails(list(destinatarios or []))
    if not to_norm:
        raise RuntimeError("No hay destinatarios.")

    cc_norm = _dedupe_emails(list(cc or []))
    # Evitar repetir en CC direcciones que ya están en Para
    to_set = {x.lower() for x in to_norm}
    cc_norm = [c for c in cc_norm if c.lower() not in to_set]

    plain = (cuerpo_texto or "").strip()
    html_body = (cuerpo_html or "").strip()
    if not plain and not html_body:
        raise RuntimeError("El cuerpo del mensaje está vacío.")
    if not plain and html_body:
        plain = html_lib.unescape(html_body.replace("<br>", "\n").replace("<br/>", "\n"))
        # Sin parser HTML completo: suficiente como respaldo para clientes solo texto
        for tag in ("<p>", "</p>", "<div>", "</div>", "<li>", "</li>"):
            plain = plain.replace(tag, "\n" if tag.startswith("</") or tag == "<li>" else "")

    msg = EmailMessage()
    msg["Subject"] = (asunto or "").strip() or "(sin asunto)"
    msg["From"] = mail_from
    msg["To"] = ", ".join(to_norm)
    if cc_norm:
        msg["Cc"] = ", ".join(cc_norm)
    msg.set_content(plain)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

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


def enviar_mail_texto_plano(app: Any, destinatarios: list[str], asunto: str, cuerpo: str, *, cc: list[str] | None = None) -> None:
    """Atajo para mensajes solo texto (p. ej. recordatorios planificación/mantenimiento)."""
    enviar_mail(app, destinatarios=destinatarios, asunto=asunto, cuerpo_texto=cuerpo, cc=cc)
