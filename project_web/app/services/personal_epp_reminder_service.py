"""Avisos por correo: entregas de ropa/EPP pendientes de confirmación del empleado."""

from __future__ import annotations

import html as html_lib
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models import EmpleadoPersonal, PersonalEntregaEpp
from app.services.deadline_alert_email_service import normalize_validate_email
from app.services.mail_link_service import login_url_for_path
from app.services.mail_service import enviar_mail, is_mail_fully_configured
from app.utils.datetime_operacion import now_operacion_naive_local

log = logging.getLogger(__name__)


def resolve_empleado_email(emp: EmpleadoPersonal | None) -> str | None:
    if emp is None:
        return None
    return normalize_validate_email((emp.email or "").strip())


def _mis_entregas_url(app: Any) -> str:
    with app.app_context():
        with app.test_request_context():
            from flask import url_for

            dest = url_for("personal.mis_entregas_epp", _external=False)
    return login_url_for_path(app, dest)


def _format_entrega_line(en: PersonalEntregaEpp) -> str:
    item = en.item.nombre if en.item else "—"
    parts = [item, en.fecha.strftime("%d/%m/%Y")]
    if (en.talle or "").strip():
        parts.append(f"talle {en.talle.strip()}")
    if en.cantidad and int(en.cantidad) > 1:
        parts.append(f"cant. {en.cantidad}")
    return " · ".join(parts)


def _build_mail_bodies(
    app: Any,
    *,
    empleado: EmpleadoPersonal,
    entregas: list[PersonalEntregaEpp],
    es_recordatorio: bool,
) -> tuple[str, str, str]:
    nombre = empleado.nombre_completo
    link = _mis_entregas_url(app)
    esc = html_lib.escape

    if len(entregas) == 1:
        en = entregas[0]
        item_nombre = en.item.nombre if en.item else "—"
        asunto = f"QDV — Confirmá tu entrega de {item_nombre}"
        intro = (
            "RRHH registró una entrega de ropa/EPP a tu nombre. "
            "Ingresá al sistema y confirmá la recepción desde tu usuario."
        )
        if es_recordatorio:
            intro = (
                "Tenés una entrega de ropa/EPP pendiente de confirmación. "
                "Ingresá al sistema para confirmar la recepción."
            )
        detalle = _format_entrega_line(en)
        devolucion = ""
        if en.prenda_anterior_entrega_id:
            if en.prenda_anterior_devuelta:
                devolucion = " Se registró la devolución de tu prenda anterior."
            else:
                devolucion = (
                    " Recordá entregar la prenda anterior a RRHH para que puedan registrar la devolución."
                )
        plain = (
            f"Hola {nombre},\n\n"
            f"{intro}{devolucion}\n\n"
            f"Detalle: {detalle}\n\n"
            f"Confirmar en el sistema: {link}\n"
        )
        html_body = (
            f"<p>Hola <strong>{esc(nombre)}</strong>,</p>"
            f"<p>{esc(intro)}{esc(devolucion)}</p>"
            f"<p><strong>Detalle:</strong> {esc(detalle)}</p>"
            f'<p><a href="{esc(link)}">Confirmar entrega en el sistema</a></p>'
            f'<p style="color:#666;font-size:12px">No responder a este mensaje.</p>'
        )
        return asunto, plain, html_body

    asunto = f"QDV — {len(entregas)} entregas de ropa/EPP pendientes de confirmación"
    intro = (
        f"Tenés {len(entregas)} entregas de ropa/EPP pendientes de confirmación. "
        "Ingresá al sistema y confirmá la recepción desde tu usuario."
    )
    lines = [_format_entrega_line(en) for en in entregas]
    plain = f"Hola {nombre},\n\n{intro}\n\n" + "\n".join(f"- {ln}" for ln in lines) + f"\n\nConfirmar: {link}\n"
    items_html = "".join(f"<li>{esc(ln)}</li>" for ln in lines)
    html_body = (
        f"<p>Hola <strong>{esc(nombre)}</strong>,</p>"
        f"<p>{esc(intro)}</p>"
        f"<ul>{items_html}</ul>"
        f'<p><a href="{esc(link)}">Confirmar entregas en el sistema</a></p>'
        f'<p style="color:#666;font-size:12px">No responder a este mensaje.</p>'
    )
    return asunto, plain, html_body


def _mark_aviso_sent(entregas: list[PersonalEntregaEpp]) -> None:
    now = datetime.now(timezone.utc)
    for en in entregas:
        en.aviso_pendiente_at = now
    db.session.commit()


def _send_to_empleado(
    app: Any,
    *,
    empleado: EmpleadoPersonal,
    entregas: list[PersonalEntregaEpp],
    es_recordatorio: bool,
) -> tuple[bool, str]:
    if not entregas:
        return False, "Sin entregas."
    to_addr = resolve_empleado_email(empleado)
    if not to_addr:
        return False, f"El legajo de {empleado.nombre_completo} no tiene un email válido cargado."
    if not is_mail_fully_configured(app):
        return False, "SMTP no configurado (SMTP_HOST / MAIL_FROM)."

    asunto, plain, html_body = _build_mail_bodies(
        app, empleado=empleado, entregas=entregas, es_recordatorio=es_recordatorio
    )
    try:
        enviar_mail(
            app,
            destinatarios=[to_addr],
            asunto=asunto,
            cuerpo_html=html_body,
            cuerpo_texto=plain,
        )
    except Exception as exc:
        log.exception("Fallo envío aviso EPP empleado_id=%s", empleado.id)
        return False, f"Error SMTP: {exc}"
    _mark_aviso_sent(entregas)
    return True, f"Aviso enviado a {to_addr}."


def notify_entrega_epp_registrada(app: Any, entrega: PersonalEntregaEpp) -> tuple[bool, str]:
    """Aviso inmediato al registrar una entrega pendiente de confirmación."""
    if (entrega.estado or "").strip() != "pendiente":
        return True, ""
    emp = entrega.empleado
    if emp is None:
        return False, "Empleado no encontrado."
    return _send_to_empleado(app, empleado=emp, entregas=[entrega], es_recordatorio=False)


def _entregas_para_recordatorio_diario() -> dict[int, list[PersonalEntregaEpp]]:
    today = now_operacion_naive_local().date()
    rows = (
        db.session.query(PersonalEntregaEpp)
        .filter(PersonalEntregaEpp.estado == "pendiente")
        .order_by(PersonalEntregaEpp.fecha.desc(), PersonalEntregaEpp.id.desc())
        .all()
    )
    by_emp: dict[int, list[PersonalEntregaEpp]] = defaultdict(list)
    for en in rows:
        sent_at = en.aviso_pendiente_at
        if sent_at is not None and sent_at.date() >= today:
            continue
        by_emp[int(en.empleado_id)].append(en)
    return by_emp


def run_entrega_epp_reminders(app: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Recordatorio diario a empleados con entregas aún pendientes de confirmación."""
    grouped = _entregas_para_recordatorio_diario()
    result: dict[str, Any] = {
        "empleados_con_pendientes": len(grouped),
        "emails_attempted": 0,
        "emails_sent": 0,
        "dry_run": dry_run,
        "smtp_configured": is_mail_fully_configured(app),
        "errors": [],
    }

    if not grouped:
        result["message"] = "No hay entregas EPP/ropa pendientes que requieran recordatorio hoy."
        return result

    if not is_mail_fully_configured(app):
        result["message"] = (
            "Hay entregas pendientes pero SMTP no está configurado. No se envió ningún recordatorio."
        )
        return result

    for emp_id, entregas in grouped.items():
        emp = db.session.get(EmpleadoPersonal, emp_id)
        if emp is None:
            continue
        result["emails_attempted"] += 1
        if dry_run:
            continue
        ok, detail = _send_to_empleado(app, empleado=emp, entregas=entregas, es_recordatorio=True)
        if ok:
            result["emails_sent"] += 1
        else:
            result["errors"].append(f"{emp.nombre_completo}: {detail}")

    if dry_run:
        result["message"] = "Dry-run: no se enviaron recordatorios EPP."
        return result

    if result["emails_sent"]:
        result["message"] = f"Recordatorios EPP enviados: {result['emails_sent']}."
    elif result["errors"]:
        result["message"] = "No se pudo enviar ningún recordatorio EPP (revisá emails en legajos y SMTP)."
    else:
        result["message"] = "No había destinatarios con email válido para recordatorios EPP."
    return result


def maybe_notify_entrega_epp_pendiente(entrega: PersonalEntregaEpp) -> tuple[bool, str]:
    """Hook desde save_entrega_epp cuando hay contexto Flask."""
    if (entrega.estado or "").strip() != "pendiente":
        return True, ""
    try:
        from flask import current_app

        app = current_app._get_current_object()
    except RuntimeError:
        return True, ""
    return notify_entrega_epp_registrada(app, entrega)
