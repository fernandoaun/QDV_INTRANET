"""Link de acción de un aviso: muestra el trámite y lo resuelve con un toque (ver `accion_link_service`)."""
from __future__ import annotations

from datetime import date
from typing import Any

from io import BytesIO

from flask import Blueprint, abort, current_app, g, render_template, request, send_file

from app.extensions import db, limiter
from app.services import accion_link_service as accion_svc

bp = Blueprint("accion", __name__, url_prefix="/accion")


def _cargar_permisos(user: Any) -> None:
    """Sin sesión: los permisos del destinatario, como hace la API del bot."""
    if user is None:
        return
    from app.auth_utils import perm_sets_for_user

    p_view, p_edit = perm_sets_for_user(user)
    g._qdv_api_perms_view = set(p_view)
    g._qdv_api_perms_edit = set(p_edit)


def _form() -> dict[str, Any]:
    return {k: v for k, v in request.form.items()}


@bp.route("/<token>", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def ver(token: str):
    data, error = accion_svc.leer_token(token)
    if data is None:
        return render_template("accion/ver.html", error=error, tipo=None, ctx={}, resultado=None)
    _cargar_permisos(data["user"])
    handler = _HANDLERS[data["t"]]
    resultado = None
    if request.method == "POST":
        ok, msg = handler.ejecutar(data, request)
        resultado = {"ok": ok, "msg": msg}
    ctx = handler.contexto(data)
    return render_template("accion/ver.html", error=ctx.pop("error", ""), tipo=data["t"], ctx=ctx,
                           resultado=resultado, token=token, nombre=accion_svc.actor_label(data))


@bp.get("/<token>/documento.pdf")
@limiter.limit("30 per minute")
def documento_pdf(token: str):
    """PDF del procedimiento del trámite (revisión / aprobación)."""
    data, _error = accion_svc.leer_token(token)
    if data is None or data["t"] not in (accion_svc.SGI_REVISAR, accion_svc.SGI_APROBAR):
        abort(404)
    from app.services import sgi_procedimiento_service as proc
    from app.services.sgi_pdf_service import adjunto_difusion

    rev = proc.get_revision(int(data["id"]))
    if rev is None:
        abort(404)
    adj = adjunto_difusion(rev.documento, rev)
    if adj is None:
        abort(404)
    nombre, contenido, mime = adj
    return send_file(BytesIO(contenido), mimetype=mime, download_name=nombre, as_attachment=False, max_age=0)


# --------------------------------------------------------------------------- procedimientos


class _Sgi:
    @staticmethod
    def contexto(data: dict[str, Any]) -> dict[str, Any]:
        from app.models.sgi import ESTADO_LABELS
        from app.services import sgi_procedimiento_service as proc

        rev = proc.get_revision(int(data["id"]))
        if rev is None:
            return {"error": "El documento ya no existe."}
        user = data["user"]
        revisar = data["t"] == accion_svc.SGI_REVISAR
        puede = proc.user_can_marcar_revisado(user, rev) if revisar else proc.user_can_aprobar_revision(user, rev)
        pendiente = rev.estado == ("en_revision" if revisar else "revisado")
        return {
            "doc": rev.documento,
            "rev": rev,
            "revisar": revisar,
            "estado_label": ESTADO_LABELS.get(rev.estado, rev.estado),
            "pendiente": pendiente,
            "puede": puede and pendiente,
            "sin_usuario": user is None,
        }

    @staticmethod
    def ejecutar(data: dict[str, Any], req: Any) -> tuple[bool, str]:
        from app.services import sgi_procedimiento_service as proc

        rev = proc.get_revision(int(data["id"]))
        user = data["user"]
        if rev is None or user is None:
            return False, "No se pudo identificar tu usuario del sistema."
        revisar = data["t"] == accion_svc.SGI_REVISAR
        puede = proc.user_can_marcar_revisado(user, rev) if revisar else proc.user_can_aprobar_revision(user, rev)
        if not puede:
            return False, "Este documento ya no está pendiente de tu firma."
        actor = accion_svc.actor_label(data)
        accion = req.form.get("accion")
        if accion == "devolver":
            ok, msg = proc.devolver_a_borrador(rev.id, int(user.id), actor, req.form.get("observaciones") or "")
        elif accion == "firmar" and revisar:
            ok, msg = proc.marcar_como_revisado(rev.id, int(user.id), actor)
        elif accion == "firmar":
            ok, msg = proc.aprobar_revision(rev.id, int(user.id), actor)
        else:
            return False, "Acción no reconocida."
        if ok:
            accion_svc.registrar(data, f"{data['t']}_{accion}", "sgi_revision", rev.id, rev.documento.codigo)
        return ok, msg


# --------------------------------------------------------------------------- vacaciones


class _VacResponsable:
    @staticmethod
    def contexto(data: dict[str, Any]) -> dict[str, Any]:
        from app.models import PersonalVacacion
        from app.services import personal_service as ps

        vac = db.session.get(PersonalVacacion, int(data["id"]))
        if vac is None:
            return {"error": "La solicitud ya no existe."}
        saldo = ps.saldo_vacacion_periodo(vac.empleado_id, vac.anio, excluir_vacacion_id=vac.id)
        pendiente = (vac.estado or "").strip() in ps.ESTADOS_VACACION_PENDIENTES_RESPONSABLE
        return {
            "vac": vac,
            "saldo": saldo,
            "pendiente": pendiente,
            "puede": pendiente and ps.user_is_responsable_vacaciones(data["user"]),
            "estado_label": ps.ESTADO_VACACION_LABELS.get(vac.estado, vac.estado),
        }

    @staticmethod
    def ejecutar(data: dict[str, Any], req: Any) -> tuple[bool, str]:
        from app.services import personal_service as ps
        from app.services.personal_vacacion_mail_service import maybe_notify_empleado_vacacion_gestionada

        user = data["user"]
        if not ps.user_is_responsable_vacaciones(user):
            return False, "Ya no sos el responsable de vacaciones."
        accion = (req.form.get("accion") or "").strip()
        ok, msg, vac = ps.gestionar_vacacion_responsable(int(data["id"]), user_id=int(user.id), accion=accion, data=_form())
        if ok and vac is not None:
            maybe_notify_empleado_vacacion_gestionada(vac)
            accion_svc.registrar(data, f"vacaciones_{accion}", "personal_vacacion", vac.id)
        return ok, msg


class _VacEmpleado:
    @staticmethod
    def contexto(data: dict[str, Any]) -> dict[str, Any]:
        from app.models import PersonalVacacion
        from app.services import personal_service as ps

        vac = db.session.get(PersonalVacacion, int(data["id"]))
        if vac is None or int(vac.empleado_id) != int(data.get("emp") or 0):
            return {"error": "La solicitud ya no existe."}
        estado = (vac.estado or "").strip()
        return {"vac": vac, "estado": estado, "puede": estado in ps.ESTADOS_VACACION_PENDIENTES_EMPLEADO}

    @staticmethod
    def ejecutar(data: dict[str, Any], req: Any) -> tuple[bool, str]:
        from app.services import personal_service as ps

        user = data["user"]
        ok, msg, vac = ps.confirmar_vacacion_empleado(
            int(data["id"]), empleado_id=int(data.get("emp") or 0), user_id=int(user.id) if user else 0
        )
        if ok and vac is not None:
            accion_svc.registrar(data, "vacaciones_confirmar", "personal_vacacion", vac.id)
        return ok, msg


# --------------------------------------------------------------------------- pedidos de EPP


def _ultima_entrega_item(item_id: int) -> Any:
    from sqlalchemy import select

    from app.models import PersonalEntregaEpp

    return db.session.scalar(
        select(PersonalEntregaEpp)
        .where(PersonalEntregaEpp.item_id == int(item_id), PersonalEntregaEpp.marca != "")
        .order_by(PersonalEntregaEpp.id.desc())
        .limit(1)
    )


class _EppPedido:
    @staticmethod
    def contexto(data: dict[str, Any]) -> dict[str, Any]:
        from app.services import epp_pedidos_service as epp_ped_svc
        from app.services import personal_service as ps

        sol = epp_ped_svc.get(int(data["id"]))
        if sol is None:
            return {"error": "El pedido ya no existe."}
        from app.auth_utils import user_can_register_entregas_personal

        emp = sol.empleado
        requiere = ps.item_epp_requiere_workflow(sol.item)
        anterior = ps.ultima_entrega_confirmada_empleado_item(emp.id, sol.item_id) if requiere else None
        previa = _ultima_entrega_item(sol.item_id)
        return {
            "sol": sol,
            "emp": emp,
            "motivo_label": epp_ped_svc.MOTIVOS.get(sol.motivo, sol.motivo),
            "estado_label": epp_ped_svc.ESTADOS.get(sol.estado, sol.estado),
            "pendiente": sol.estado == "pendiente",
            "puede": sol.estado == "pendiente" and user_can_register_entregas_personal(data["user"]),
            "anterior": anterior,
            "hoy": date.today().isoformat(),
            "pre": {
                "tipo_modelo": previa.tipo_modelo if previa else "",
                "marca": previa.marca if previa else "",
                "certificacion": previa.certificacion if previa else "",
            },
            "falta_dni": not (emp.dni or "").strip(),
            "falta_puesto": not ((emp.epp_descripcion_puesto or "").strip() or (emp.puesto or "").strip()),
        }

    @staticmethod
    def ejecutar(data: dict[str, Any], req: Any) -> tuple[bool, str]:
        from app.auth_utils import user_can_register_entregas_personal
        from app.services import epp_pedidos_service as epp_ped_svc
        from app.services import personal_service as ps

        user = data["user"]
        if not user_can_register_entregas_personal(user):
            return False, "Tu usuario no puede registrar entregas de EPP."
        sol = epp_ped_svc.get(int(data["id"]))
        if sol is None or sol.estado != "pendiente":
            return False, "Ese pedido ya fue resuelto."
        accion = req.form.get("accion")
        if accion == "rechazar":
            err = epp_ped_svc.rechazar(sol, req.form.get("respuesta") or "", int(user.id))
            if err:
                db.session.rollback()
                return False, err
            db.session.commit()
            epp_ped_svc.avisar_rechazo(current_app._get_current_object(), sol)
            accion_svc.registrar(data, "epp_pedido_rechazar", "personal_solicitud_epp", sol.id)
            return True, "Pedido rechazado. Le avisamos al empleado."
        if accion != "entregar":
            return False, "Acción no reconocida."
        form = _form()
        form.update({
            "empleado_id": str(sol.empleado_id),
            "item_id": str(sol.item_id),
            "solicitud_id": str(sol.id),
            "epp_asignados": [str(sol.item_id)],
        })
        ok, msg = ps.save_entrega_epp(form, user_id=int(user.id))
        if ok:
            accion_svc.registrar(data, "epp_pedido_entregar", "personal_solicitud_epp", sol.id)
        return ok, msg


# --------------------------------------------------------------------------- vencimientos


class _Vencimiento:
    @staticmethod
    def contexto(data: dict[str, Any]) -> dict[str, Any]:
        from app.services import vencimiento_service as vs

        v = vs.get_vencimiento(int(data["id"]))
        if v is None:
            return {"error": "El vencimiento ya no existe."}
        sucesor = None
        if not v.activo:
            from sqlalchemy import select

            from app.models import Vencimiento

            sucesor = db.session.scalar(select(Vencimiento).where(Vencimiento.continuacion_de_id == v.id).limit(1))
        return {"v": v, "dias": vs.dias_restantes(v.fecha_vencimiento), "puede": bool(v.activo), "sucesor": sucesor}

    @staticmethod
    def ejecutar(data: dict[str, Any], req: Any) -> tuple[bool, str]:
        from app.services import vencimiento_service as vs

        v = vs.get_vencimiento(int(data["id"]))
        if v is None or not v.activo:
            return False, "Este vencimiento ya fue renovado o dado de baja."
        nueva = vs.parse_iso_date(req.form.get("nueva_fecha"))
        if nueva is None:
            return False, "Indicá la nueva fecha de vencimiento."
        if nueva <= v.fecha_vencimiento:
            return False, "La nueva fecha tiene que ser posterior al vencimiento actual."
        user = data["user"]
        actor = accion_svc.actor_label(data)
        nuevo, msg = vs.renew_vencimiento(v.id, nueva, int(user.id) if user else None, actor)
        if nuevo is None:
            return False, msg
        archivo = req.files.get("archivo")
        if archivo is not None and archivo.filename:
            ok_a, msg_a = vs.save_attachment(nuevo.id, archivo, int(user.id) if user else None, actor)
            msg = f"{msg} {msg_a}" if ok_a else f"{msg} El archivo no se pudo guardar: {msg_a}"
        accion_svc.registrar(data, "vencimiento_renovar", "vencimiento", v.id, f"nueva fecha {nueva.isoformat()}")
        return True, msg


# --------------------------------------------------------------------------- tareas (planificación / mantenimiento)


class _Tareas:
    @staticmethod
    def contexto(data: dict[str, Any]) -> dict[str, Any]:
        from app.models import MaintenanceOrder, PlanificacionActividad
        from app.services import planificacion_service as plan_svc

        actividades = [a for a in (db.session.get(PlanificacionActividad, int(i)) for i in data.get("p") or []) if a]
        ordenes = [o for o in (db.session.get(MaintenanceOrder, int(i)) for i in data.get("o") or []) if o]
        return {
            "actividades": actividades,
            "ordenes": ordenes,
            "codigo": plan_svc.actividad_display_codigo,
            "estado_act": plan_svc.ESTADO_LABELS,
        }

    @staticmethod
    def ejecutar(data: dict[str, Any], req: Any) -> tuple[bool, str]:
        from app.models import MaintenanceOrder, PlanificacionActividad
        from app.services import mantenimiento_service as ms
        from app.services import planificacion_service as plan_svc

        accion = (req.form.get("accion") or "").strip()
        tipo, _, raw = accion.partition(":")
        if not raw.isdigit():
            return False, "Acción no reconocida."
        oid = int(raw)
        if tipo == "act" and oid in [int(i) for i in data.get("p") or []]:
            a = db.session.get(PlanificacionActividad, oid)
            if a is None or a.estado in ("finalizada", "cancelada"):
                return False, "Esa actividad ya estaba cerrada."
            deps = plan_svc.dependencias_entrantes_por_sucesora([a.id]).get(a.id, [])
            err = plan_svc.validate_estado_con_dependencias(a, a.estado, "finalizada", deps)
            if err:
                return False, err
            a.estado = "finalizada"
            db.session.commit()
            accion_svc.registrar(data, "planificacion_cumplida", "planificacion_actividad", a.id)
            return True, f"«{a.titulo}» quedó cumplida."
        if tipo == "ord" and oid in [int(i) for i in data.get("o") or []]:
            o = db.session.get(MaintenanceOrder, oid)
            if o is None or o.estado in ("finalizado", "cancelado"):
                return False, "Esa orden ya estaba cerrada."
            ms.finalizar_orden(o, req.form.get(f"resultado_{oid}") or "")
            db.session.commit()
            accion_svc.registrar(data, "orden_finalizada", "maintenance_order", o.id)
            return True, f"Orden #{o.id} finalizada."
        return False, "Ese ítem no es de este aviso."


_HANDLERS: dict[str, Any] = {
    accion_svc.SGI_REVISAR: _Sgi,
    accion_svc.SGI_APROBAR: _Sgi,
    accion_svc.VAC_RESPONSABLE: _VacResponsable,
    accion_svc.VAC_EMPLEADO: _VacEmpleado,
    accion_svc.EPP_PEDIDO: _EppPedido,
    accion_svc.VENCIMIENTO: _Vencimiento,
    accion_svc.TAREAS: _Tareas,
}
