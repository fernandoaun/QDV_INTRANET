"""Pedidos de ropa/EPP que hace el personal desde la plataforma.

El empleado pide desde «Mis entregas EPP»; le llega un mail a la responsable de laboratorio, que entrega
(registra la entrega con los datos del pedido: sigue el circuito de confirmación y constancia de siempre)
o rechaza con un motivo. Pedir verbalmente sigue siendo válido: se registra la entrega directo.
"""
from __future__ import annotations

import html as html_lib
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, select

from app.extensions import db
from app.models import EmpleadoPersonal, PersonalEppItem, PersonalSolicitudEpp, User
from app.services.deadline_alert_email_service import normalize_validate_email
from app.user_roles import ROLE_RESPONSABLE_LABORATORIO, normalize_stored_rol

log = logging.getLogger(__name__)

MOTIVOS: dict[str, str] = {
    "rotura": "Rotura",
    "desgaste": "Desgaste",
    "perdida": "Pérdida",
    "talle": "Cambio de talle",
    "falta": "Me falta / primera vez",
    "otro": "Otro",
}
ESTADOS: dict[str, str] = {
    "pendiente": "Pendiente",
    "entregada": "Entregada",
    "rechazada": "Rechazada",
    "cancelada": "Cancelada",
}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def fecha_local(dt: datetime | None) -> str:
    if dt is None:
        return ""
    from app.utils.datetime_operacion import operacion_zoneinfo

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(operacion_zoneinfo()).strftime("%d/%m/%Y %H:%M")


def labels_context() -> dict[str, Any]:
    return {"motivos_pedido_epp": MOTIVOS, "estados_pedido_epp": ESTADOS, "fecha_local_pedido": fecha_local}


def get(solicitud_id: int) -> PersonalSolicitudEpp | None:
    return db.session.get(PersonalSolicitudEpp, int(solicitud_id))


def del_empleado(empleado_id: int, limit: int = 30) -> list[PersonalSolicitudEpp]:
    return list(
        db.session.scalars(
            select(PersonalSolicitudEpp)
            .where(PersonalSolicitudEpp.empleado_id == int(empleado_id))
            .order_by(PersonalSolicitudEpp.created_at.desc())
            .limit(limit)
        ).unique()
    )


def listar(limit: int = 200) -> list[PersonalSolicitudEpp]:
    """Pendientes primero (más viejos arriba), después el resto por fecha."""
    pendiente_primero = case((PersonalSolicitudEpp.estado == "pendiente", 0), else_=1)
    return list(
        db.session.scalars(
            select(PersonalSolicitudEpp)
            .order_by(pendiente_primero, PersonalSolicitudEpp.created_at.asc())
            .limit(limit)
        ).unique()
    )


def contar_pendientes() -> int:
    from sqlalchemy import func

    return int(
        db.session.scalar(
            select(func.count(PersonalSolicitudEpp.id)).where(PersonalSolicitudEpp.estado == "pendiente")
        )
        or 0
    )


def crear(empleado: EmpleadoPersonal, data: Any, user_id: int | None) -> tuple[PersonalSolicitudEpp | None, str | None]:
    raw_item = (data.get("item_id") or "").strip()
    item = db.session.get(PersonalEppItem, int(raw_item)) if raw_item.isdigit() else None
    if item is None or not item.activo:
        return None, "Elegí qué necesitás de la lista."
    motivo = (data.get("motivo") or "").strip()
    if motivo not in MOTIVOS:
        return None, "Elegí el motivo del pedido."
    raw_cant = (data.get("cantidad") or "1").strip()
    cantidad = int(raw_cant) if raw_cant.isdigit() and 1 <= int(raw_cant) <= 20 else 0
    if not cantidad:
        return None, "La cantidad tiene que estar entre 1 y 20."
    comentario = (data.get("comentario") or "").strip()[:1000]
    if motivo == "otro" and not comentario:
        return None, "Contá brevemente el motivo en el comentario."
    sol = PersonalSolicitudEpp(
        empleado_id=empleado.id,
        item_id=item.id,
        talle=(data.get("talle") or "").strip()[:32],
        cantidad=cantidad,
        motivo=motivo,
        comentario=comentario,
        created_by_user_id=user_id,
    )
    db.session.add(sol)
    db.session.flush()
    return sol, None


def cancelar(sol: PersonalSolicitudEpp, empleado: EmpleadoPersonal) -> str | None:
    if sol.empleado_id != empleado.id:
        return "Ese pedido no es tuyo."
    if sol.estado != "pendiente":
        return "Solo se pueden cancelar pedidos pendientes."
    sol.estado = "cancelada"
    sol.resuelta_at = _ahora()
    return None


def rechazar(sol: PersonalSolicitudEpp, motivo: str, user_id: int | None) -> str | None:
    if sol.estado != "pendiente":
        return "Ese pedido ya fue resuelto."
    motivo = (motivo or "").strip()[:1000]
    if not motivo:
        return "Escribí el motivo del rechazo: le llega al empleado."
    sol.estado = "rechazada"
    sol.respuesta = motivo
    sol.resuelta_at = _ahora()
    sol.resuelta_by_user_id = user_id
    return None


def marcar_entregada(solicitud_id: Any, entrega_id: int, empleado_id: int, user_id: int | None) -> None:
    """Al registrar la entrega desde un pedido, lo cierra y lo vincula. No hace commit."""
    raw = str(solicitud_id or "").strip()
    if not raw.isdigit():
        return
    sol = get(int(raw))
    if sol is None or sol.estado != "pendiente" or sol.empleado_id != int(empleado_id):
        return
    sol.estado = "entregada"
    sol.entrega_id = int(entrega_id)
    sol.resuelta_at = _ahora()
    sol.resuelta_by_user_id = user_id


# ---------------------------------------------------------------- avisos por mail


def destinatarios_responsables(app: Any) -> list[str]:
    """Mail del legajo de quienes tienen perfil Responsable de laboratorio; si ninguno tiene, la lista general de avisos."""
    out: list[str] = []
    usuarios = db.session.scalars(select(User).where(User.activo.is_(True))).all()
    for u in usuarios:
        if u.is_admin or normalize_stored_rol(u.rol) != ROLE_RESPONSABLE_LABORATORIO:
            continue
        emp = db.session.scalar(select(EmpleadoPersonal).where(EmpleadoPersonal.user_id == u.id))
        mail = normalize_validate_email((emp.email or "").strip()) if emp is not None else None
        if mail and mail not in out:
            out.append(mail)
    if out:
        return out
    from app.services.deadline_alert_email_service import merged_recipient_addresses

    return merged_recipient_addresses(app)


def _enviar(app: Any, destinatarios: list[str], asunto: str, parrafos: list[str], link: str, link_texto: str) -> tuple[bool, str]:
    from app.services.mail_link_service import require_absolute_mail_url
    from app.services.mail_service import enviar_mail, is_mail_fully_configured

    if not destinatarios:
        return False, "no hay destinatario con mail cargado"
    if not is_mail_fully_configured(app):
        return False, "el correo del sistema no está configurado"
    ok, detalle = require_absolute_mail_url(app, link, context="pedido EPP")
    if not ok:
        return False, detalle
    esc = html_lib.escape
    plain = "\n\n".join(parrafos) + f"\n\n{link_texto}: {link}\n"
    html_body = "".join(f"<p>{esc(p)}</p>" for p in parrafos) + f'<p><a href="{esc(link)}">{esc(link_texto)}</a></p>' + (
        '<p style="color:#666;font-size:12px">No responder a este mensaje.</p>'
    )
    try:
        enviar_mail(app, destinatarios=destinatarios, asunto=asunto, cuerpo_html=html_body, cuerpo_texto=plain)
    except Exception as exc:  # el pedido queda registrado aunque falle el mail
        log.warning("Pedido EPP: no se pudo enviar el mail: %s", exc)
        return False, "no se pudo enviar el mail"
    return True, ""


def _detalle(sol: PersonalSolicitudEpp) -> str:
    partes = [sol.item.nombre if sol.item else "—", f"cantidad {sol.cantidad}"]
    if sol.talle:
        partes.append(f"talle {sol.talle}")
    partes.append(f"motivo: {MOTIVOS.get(sol.motivo, sol.motivo)}")
    return " · ".join(partes)


def avisar_nuevo_pedido(app: Any, sol: PersonalSolicitudEpp) -> tuple[bool, str]:
    from app.services.mail_link_service import public_abs_url

    nombre = sol.empleado.nombre_completo if sol.empleado else "Un empleado"
    parrafos = [f"{nombre} pidió ropa/EPP desde la plataforma.", f"Pedido: {_detalle(sol)}."]
    if sol.comentario:
        parrafos.append(f"Comentario: {sol.comentario}")
    return _enviar(
        app,
        destinatarios_responsables(app),
        f"QDV — Pedido de EPP de {nombre}",
        parrafos,
        public_abs_url(app, "personal.epp_pedidos"),
        "Ver pedidos de EPP",
    )


def avisar_rechazo(app: Any, sol: PersonalSolicitudEpp) -> tuple[bool, str]:
    from app.services.mail_link_service import public_abs_url
    from app.services.personal_epp_reminder_service import resolve_empleado_email

    to = resolve_empleado_email(sol.empleado)
    nombre = sol.empleado.nombre_completo if sol.empleado else ""
    return _enviar(
        app,
        [to] if to else [],
        "QDV — Tu pedido de EPP no fue aprobado",
        [f"Hola {nombre},", f"Tu pedido ({_detalle(sol)}) no fue aprobado.", f"Motivo: {sol.respuesta}"],
        public_abs_url(app, "personal.mis_entregas_epp"),
        "Ver mis pedidos",
    )
