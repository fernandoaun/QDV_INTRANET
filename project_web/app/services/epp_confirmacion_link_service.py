"""
Confirmación de entregas de ropa/EPP con un link (sin usuario ni contraseña).

El aviso por mail (y su copia por WhatsApp) lleva un link firmado con el legajo y las entregas;
el empleado lo abre en el celular y confirma con un botón. El link solo le llega a él y vence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db
from app.models import EmpleadoPersonal, PersonalEntregaEpp
from app.services import security_audit_service as audit_svc
from app.services.personal_service import item_epp_requiere_workflow

LINK_MAX_AGE_SEC = 30 * 24 * 3600
_SALT = "qdv-epp-confirmar-link-v1"


def _serializer(app: Any = None) -> URLSafeTimedSerializer:
    app = app or current_app
    return URLSafeTimedSerializer(str(app.config["SECRET_KEY"]), salt=_SALT)


def crear_token(app: Any, empleado: EmpleadoPersonal, entregas: list[PersonalEntregaEpp]) -> str:
    return _serializer(app).dumps({"emp": int(empleado.id), "ids": sorted(int(en.id) for en in entregas)})


def leer_token(token: str) -> tuple[EmpleadoPersonal | None, list[PersonalEntregaEpp], str]:
    """(empleado, entregas del link, error). Las entregas vienen en cualquier estado."""
    try:
        data = _serializer().loads(token, max_age=LINK_MAX_AGE_SEC)
    except SignatureExpired:
        return None, [], "El link venció. Pedile a RRHH que te reenvíe el aviso o confirmá desde el sistema."
    except BadSignature:
        return None, [], "El link no es válido."
    emp = db.session.get(EmpleadoPersonal, int(data.get("emp") or 0))
    if emp is None:
        return None, [], "No se encontró el legajo."
    ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()]
    entregas = [
        en
        for en in (db.session.get(PersonalEntregaEpp, i) for i in ids)
        if en is not None and int(en.empleado_id) == int(emp.id)
    ]
    return emp, entregas, ""


def motivo_no_confirmable(entrega: PersonalEntregaEpp) -> str:
    """Vacío si se puede confirmar por link; si no, el motivo para mostrar."""
    if entrega.estado != "pendiente":
        return "Ya confirmada."
    if not item_epp_requiere_workflow(entrega.item):
        return "No requiere confirmación."
    if entrega.prenda_anterior_entrega_id is not None and not entrega.prenda_anterior_devuelta:
        return "Primero entregá la prenda anterior a RRHH para que registren la devolución."
    return ""


def confirmar(empleado: EmpleadoPersonal, entregas: list[PersonalEntregaEpp]) -> int:
    """Confirma las entregas confirmables del link. Devuelve cuántas confirmó."""
    ahora = datetime.now(timezone.utc)
    confirmadas: list[PersonalEntregaEpp] = []
    for en in entregas:
        if motivo_no_confirmable(en):
            continue
        en.estado = "confirmada"
        en.confirmada_at = ahora
        en.confirmada_by_user_id = empleado.user_id
        confirmadas.append(en)
    if not confirmadas:
        return 0
    db.session.commit()
    actor = empleado.user
    for en in confirmadas:
        audit_svc.record_event(
            action="epp_confirmada_link",
            module="personal",
            actor=actor,
            actor_username=None if actor else empleado.nombre_completo,
            entity_type="personal_entrega_epp",
            entity_id=int(en.id),
            detail=f"empleado_id={empleado.id} (link del aviso)",
        )
    return len(confirmadas)
