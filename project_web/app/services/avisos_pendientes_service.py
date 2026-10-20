"""Trámites pendientes de una persona, para resolverlos respondiendo por WhatsApp (sin link ni sistema).

Son los mismos que llegan con link de acción por mail (`accion_link_service`): revisar o aprobar un
procedimiento, gestionar o aceptar vacaciones, entregar un pedido de EPP, renovar un vencimiento y cerrar
tareas de planificación/mantenimiento. El bot lista `pendientes(user)` y, con la respuesta de la persona,
arma `responder` (preview → confirmación → ejecutar), que corre la misma lógica que la pantalla del link.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from flask import current_app
from sqlalchemy import select
from werkzeug.datastructures import MultiDict

from app.extensions import db
from app.models import User
from app.services import accion_link_service as accion_svc

MAX_POR_TIPO = 10

# Qué puede responder la persona en cada trámite (clave del bot → acción y campos de la pantalla).
ACCIONES: dict[str, dict[str, str]] = {
    accion_svc.SGI_REVISAR: {"revisado": "Marcar como revisado", "devolver": "Devolver con observaciones (campo observaciones)"},
    accion_svc.SGI_APROBAR: {"aprobar": "Aprobar", "devolver": "Devolver con observaciones (campo observaciones)"},
    accion_svc.VAC_RESPONSABLE: {
        "aprobar": "Aprobar",
        "rechazar": "Rechazar (campo motivo)",
        "proponer": "Proponer otras fechas (campos desde, hasta; motivo opcional)",
    },
    accion_svc.VAC_EMPLEADO: {"aceptar": "Aceptar (las fechas propuestas o el rechazo)"},
    accion_svc.EPP_PEDIDO: {
        "entregar": "Registrar la entrega (campos de la constancia; vienen precargados)",
        "rechazar": "Rechazar (campo motivo)",
    },
    accion_svc.VENCIMIENTO: {"renovar": "Registrar la renovación (campo nueva_fecha AAAA-MM-DD)"},
    "epp_recibido": {"recibido": "Confirmar que recibió la ropa/EPP"},
    "actividad": {"cumplida": "Marcar cumplida"},
    "orden": {"finalizada": "Marcar finalizada (campo resultado opcional)"},
}


def _emails(user: User) -> set[str]:
    from app.services.sgi_difusion_mail_service import _user_emails

    return {e.lower() for e in _user_emails(user)}


def _avisos_generales(app: Any) -> set[str]:
    from app.services.deadline_alert_email_service import merged_recipient_addresses

    return {e.lower() for e in merged_recipient_addresses(app)}


def _item(clave: str, titulo: str, detalle: str, **extra: Any) -> dict[str, Any]:
    tipo = clave.split(":", 1)[0]
    return {"pendiente": clave, "tipo": tipo, "titulo": titulo, "detalle": detalle,
            "acciones": ACCIONES[tipo], **extra}


def pendientes(user: User) -> list[dict[str, Any]]:
    app = current_app._get_current_object()
    mails = _emails(user)
    out: list[dict[str, Any]] = []
    out += _sgi(app, user, mails)
    out += _vacaciones(user)
    out += _epp_recibido(user)
    out += _epp(app, user, mails)
    generales = bool(mails & _avisos_generales(app))
    out += _vencimientos(user, mails, generales)
    if generales:
        out += _tareas()
    return out


def _sgi(app: Any, user: User, mails: set[str]) -> list[dict[str, Any]]:
    from app.models.sgi import SgiProcedimientoRevision
    from app.services import sgi_procedimiento_service as proc
    from app.services import sgi_workflow_service as wf

    out = []
    revs = db.session.scalars(
        select(SgiProcedimientoRevision).where(SgiProcedimientoRevision.estado.in_(("en_revision", "revisado")))
    ).all()
    for rev in revs:
        revisar = rev.estado == "en_revision"
        dest = wf.resolve_revision_recipients(app, rev) if revisar else wf.resolve_approval_recipients(app, rev)
        if not mails & {d.lower() for d in dest}:
            continue
        puede = proc.user_can_marcar_revisado(user, rev) if revisar else proc.user_can_aprobar_revision(user, rev)
        if not puede:
            continue
        doc = rev.documento
        tipo = accion_svc.SGI_REVISAR if revisar else accion_svc.SGI_APROBAR
        out.append(_item(f"{tipo}:{rev.id}", f"{'Revisar' if revisar else 'Aprobar'} {doc.codigo} — {doc.titulo}",
                         rev.revision_label))
    return out[:MAX_POR_TIPO]


def _vacaciones(user: User) -> list[dict[str, Any]]:
    from app.models import PersonalVacacion
    from app.services import personal_service as ps

    out = []
    if ps.user_is_responsable_vacaciones(user):
        for vac in db.session.scalars(
            select(PersonalVacacion).where(PersonalVacacion.estado.in_(tuple(ps.ESTADOS_VACACION_PENDIENTES_RESPONSABLE)))
            .order_by(PersonalVacacion.fecha_desde).limit(MAX_POR_TIPO)
        ):
            nombre = vac.empleado.nombre_completo if vac.empleado else "—"
            out.append(_item(f"{accion_svc.VAC_RESPONSABLE}:{vac.id}", f"Vacaciones de {nombre}",
                             f"{vac.fecha_desde.strftime('%d/%m/%Y')} al {vac.fecha_hasta.strftime('%d/%m/%Y')} ({vac.dias} días)"
                             + (f" · {vac.observaciones}" if vac.observaciones else "")))
    emp = ps.resolve_empleado_for_user(user, commit=False)
    if emp is not None:
        for vac in db.session.scalars(
            select(PersonalVacacion).where(
                PersonalVacacion.empleado_id == emp.id,
                PersonalVacacion.estado.in_(tuple(ps.ESTADOS_VACACION_PENDIENTES_EMPLEADO)),
            )
        ):
            que = "propuesta de nuevas fechas" if vac.estado == "modificada" else "solicitud rechazada"
            out.append(_item(f"{accion_svc.VAC_EMPLEADO}:{vac.id}", f"Tus vacaciones: {que}",
                             f"{vac.fecha_desde.strftime('%d/%m/%Y')} al {vac.fecha_hasta.strftime('%d/%m/%Y')}"
                             + (f" · Motivo: {vac.motivo_responsable}" if vac.motivo_responsable else "")))
    return out


def _epp(app: Any, user: User, mails: set[str]) -> list[dict[str, Any]]:
    from app.auth_utils import user_can_register_entregas_personal
    from app.models import PersonalSolicitudEpp
    from app.services import epp_pedidos_service as eps
    from app.web.modules.accion.routes import _EppPedido

    if not user_can_register_entregas_personal(user):
        return []
    if not mails & {d.lower() for d in eps.destinatarios_responsables(app)} and not user.is_admin:
        return []
    out = []
    for sol in db.session.scalars(
        select(PersonalSolicitudEpp).where(PersonalSolicitudEpp.estado == "pendiente")
        .order_by(PersonalSolicitudEpp.created_at).limit(MAX_POR_TIPO)
    ):
        ctx = _EppPedido.contexto({"id": sol.id, "user": user})
        campos = {"fecha": ctx["hoy"], "cantidad": sol.cantidad, "talle": sol.talle or "", **ctx["pre"]}
        faltan = [c for c, falta in (("emp_dni", ctx["falta_dni"]), ("epp_descripcion_puesto", ctx["falta_puesto"])) if falta]
        if ctx["anterior"] is not None:
            faltan.append("prenda_anterior_devuelta (confirmar que devolvió la anterior: «1»)")
        out.append(_item(f"{accion_svc.EPP_PEDIDO}:{sol.id}",
                         f"Pedido de EPP de {sol.empleado.nombre_completo if sol.empleado else '—'}",
                         eps._detalle(sol) + (f" · {sol.comentario}" if sol.comentario else ""),
                         campos_entrega=campos, faltan_para_entregar=faltan))
    return out


def _epp_entregas_pendientes(user: User) -> tuple[Any, list[Any]]:
    from app.models import PersonalEntregaEpp
    from app.services import epp_confirmacion_link_service as link_svc
    from app.services import personal_service as ps

    emp = ps.resolve_empleado_for_user(user, commit=False)
    if emp is None:
        return None, []
    entregas = db.session.scalars(
        select(PersonalEntregaEpp).where(PersonalEntregaEpp.empleado_id == emp.id, PersonalEntregaEpp.estado == "pendiente")
    ).all()
    return emp, [en for en in entregas if not link_svc.motivo_no_confirmable(en)]


def _epp_recibido(user: User) -> list[dict[str, Any]]:
    emp, entregas = _epp_entregas_pendientes(user)
    if not entregas:
        return []
    detalle = "; ".join(
        f"{en.item.nombre if en.item else '—'} ({en.fecha.strftime('%d/%m/%Y')}{f', talle {en.talle}' if en.talle else ''})"
        for en in entregas
    )
    return [_item(f"epp_recibido:{emp.id}", "Confirmar entrega de ropa/EPP", detalle)]


def _vencimientos(user: User, mails: set[str], generales: bool) -> list[dict[str, Any]]:
    from app.models import Vencimiento

    out = []
    for v in db.session.scalars(
        select(Vencimiento).where(Vencimiento.activo.is_(True), Vencimiento.aviso_30_dias_enviado.is_(True))
        .order_by(Vencimiento.fecha_vencimiento)
    ):
        if not (generales or (v.email_aviso or "").strip().lower() in mails):
            continue
        out.append(_item(f"{accion_svc.VENCIMIENTO}:{v.id}", f"Vencimiento: {v.nombre}",
                         f"vence el {v.fecha_vencimiento.strftime('%d/%m/%Y')}"))
        if len(out) >= MAX_POR_TIPO:
            break
    return out


def _tareas() -> list[dict[str, Any]]:
    from app.models import DeadlineReminderSent, MaintenanceOrder, PlanificacionActividad
    from app.services import deadline_reminder_service as drs
    from app.services import planificacion_service as plan_svc

    def avisadas(dominio: str) -> Any:
        return select(DeadlineReminderSent.entity_id).where(DeadlineReminderSent.domain == dominio)

    out = []
    for a in db.session.scalars(
        select(PlanificacionActividad).where(
            PlanificacionActividad.estado.notin_(("finalizada", "cancelada")),
            PlanificacionActividad.id.in_(avisadas(drs.DOMAIN_PLANIFICACION)),
        ).order_by(PlanificacionActividad.fecha_fin).limit(MAX_POR_TIPO)
    ):
        out.append(_item(f"actividad:{a.id}", f"[{plan_svc.actividad_display_codigo(a)}] {a.titulo}",
                         f"planificación · fin {a.fecha_fin.strftime('%d/%m/%Y')}"))
    for o in db.session.scalars(
        select(MaintenanceOrder).where(
            MaintenanceOrder.estado.notin_(("finalizado", "cancelado")),
            MaintenanceOrder.id.in_(avisadas(drs.DOMAIN_MANTENIMIENTO_ORDER)),
        ).order_by(MaintenanceOrder.fecha_programada).limit(MAX_POR_TIPO)
    ):
        eq = o.equipo.nombre_equipo if o.equipo else "—"
        out.append(_item(f"orden:{o.id}", f"Orden #{o.id} — {eq}", f"mantenimiento {o.tipo_mantenimiento} · {o.fecha_programada}"))
    return out


# ------------------------------------------------------------------ responder


def _buscar(user: User, clave: str) -> dict[str, Any]:
    for p in pendientes(user):
        if p["pendiente"] == clave:
            return p
    raise ValueError("Eso ya no está pendiente para vos (o no te corresponde). Pedí la lista de pendientes.")


def _form_y_datos(user: User, clave: str, accion: str, campos: dict[str, Any]) -> tuple[str, dict[str, Any], MultiDict]:
    tipo, _, raw = clave.partition(":")
    oid = int(raw)
    email = next(iter(sorted(_emails(user))), "")
    data: dict[str, Any] = {"t": tipo, "id": oid, "user": user, "e": email}
    form: dict[str, Any] = {}
    c = {k: ("" if v is None else str(v)) for k, v in (campos or {}).items()}
    if tipo in (accion_svc.SGI_REVISAR, accion_svc.SGI_APROBAR):
        form = {"accion": "devolver" if accion == "devolver" else "firmar", "observaciones": c.get("observaciones", "")}
    elif tipo == accion_svc.VAC_RESPONSABLE:
        acc = {"aprobar": "aprobar", "rechazar": "rechazar", "proponer": "modificar"}[accion]
        form = {"accion": acc, "motivo_responsable": c.get("motivo", ""),
                "fecha_desde": c.get("desde", ""), "fecha_hasta": c.get("hasta", "")}
    elif tipo == accion_svc.VAC_EMPLEADO:
        from app.services import personal_service as ps

        emp = ps.resolve_empleado_for_user(user, commit=False)
        data["emp"] = int(emp.id) if emp else 0
    elif tipo == accion_svc.EPP_PEDIDO:
        if accion == "rechazar":
            form = {"accion": "rechazar", "respuesta": c.get("motivo", "")}
        else:
            form = {"accion": "entregar", **c}
    elif tipo == accion_svc.VENCIMIENTO:
        form = {"nueva_fecha": c.get("nueva_fecha", "")}
    elif tipo == "actividad":
        data.update({"t": accion_svc.TAREAS, "p": [oid], "o": []})
        form = {"accion": f"act:{oid}"}
    elif tipo == "orden":
        data.update({"t": accion_svc.TAREAS, "p": [], "o": [oid]})
        form = {"accion": f"ord:{oid}", f"resultado_{oid}": c.get("resultado", "")}
    return tipo, data, MultiDict(form)


def preview(user: User, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    clave = str(payload.get("pendiente") or "").strip()
    accion = str(payload.get("accion") or "").strip().lower()
    campos = payload.get("campos") if isinstance(payload.get("campos"), dict) else {}
    item = _buscar(user, clave)
    if accion not in item["acciones"]:
        raise ValueError(f"Para «{item['titulo']}» podés: " + ", ".join(item["acciones"]))
    if item["tipo"] == accion_svc.EPP_PEDIDO and accion == "entregar":
        campos = {**item["campos_entrega"], **campos}
    resumen = f"{item['titulo']} → {item['acciones'][accion].split(' (')[0]}"
    datos = {k: v for k, v in campos.items() if str(v).strip()}
    if datos:
        resumen += " · " + ", ".join(f"{k}: {v}" for k, v in datos.items())
    return resumen, {"pendiente": clave, "accion": accion, "campos": campos}


def ejecutar(user: User, payload: dict[str, Any]) -> dict[str, Any]:
    from app.web.modules.accion.routes import _HANDLERS

    clave, accion, campos = payload["pendiente"], payload["accion"], payload.get("campos") or {}
    _buscar(user, clave)
    if clave.startswith("epp_recibido:"):
        from app.services import epp_confirmacion_link_service as link_svc

        emp, entregas = _epp_entregas_pendientes(user)
        n = link_svc.confirmar(emp, entregas) if emp is not None else 0
        if not n:
            raise ValueError("No había entregas para confirmar.")
        return {"id": int(emp.id), "message": f"Listo, quedó registrado que recibiste {n} {'entregas' if n > 1 else 'entrega'}."}
    tipo, data, form = _form_y_datos(user, clave, accion, campos)
    handler = _HANDLERS[data["t"]]
    ok, msg = handler.ejecutar(data, SimpleNamespace(form=form, files={}))
    if not ok:
        raise ValueError(msg)
    return {"id": data["id"], "message": msg}
