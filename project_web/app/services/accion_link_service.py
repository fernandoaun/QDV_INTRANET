"""Links de acción de los avisos (mail y WhatsApp): la persona resuelve desde el celular sin entrar al sistema.

Cada aviso que pide algo (revisar o aprobar un procedimiento, gestionar vacaciones, entregar un pedido de EPP,
renovar un vencimiento, cerrar tareas) lleva un link firmado con el trámite y el destinatario. El link solo
sirve para ese trámite, vence, y lo que se hace queda registrado a nombre de quien lo recibió, igual que
desde la PC. Mismo esquema que la confirmación de entregas de EPP (`epp_confirmacion_link_service`).
"""
from __future__ import annotations

from typing import Any

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select

from app.extensions import db
from app.models import EmpleadoPersonal, User

_SALT = "qdv-accion-link-v1"
VIGENCIA_DIAS = 30

# Tipos de trámite (cada uno con su pantalla en app/web/modules/accion).
SGI_REVISAR = "sgi_revisar"
SGI_APROBAR = "sgi_aprobar"
VAC_RESPONSABLE = "vac_responsable"
VAC_EMPLEADO = "vac_empleado"
EPP_PEDIDO = "epp_pedido"
VENCIMIENTO = "vencimiento"
TAREAS = "tareas"
TIPOS = frozenset({SGI_REVISAR, SGI_APROBAR, VAC_RESPONSABLE, VAC_EMPLEADO, EPP_PEDIDO, VENCIMIENTO, TAREAS})


def _serializer(app: Any = None) -> URLSafeTimedSerializer:
    app = app or current_app
    return URLSafeTimedSerializer(str(app.config["SECRET_KEY"]), salt=_SALT)


def usuario_por_email(email: str | None) -> User | None:
    """Usuario activo dueño de ese mail: por el legajo (mail del legajo) o por el nombre de usuario."""
    e = (email or "").strip().lower()
    if not e:
        return None
    emp = db.session.scalar(
        select(EmpleadoPersonal)
        .where(func.lower(func.trim(EmpleadoPersonal.email)) == e, EmpleadoPersonal.user_id.isnot(None))
        .limit(1)
    )
    if emp is not None:
        u = db.session.get(User, int(emp.user_id))
        if u is not None and u.activo:
            return u
    u = db.session.scalar(select(User).where(func.lower(User.username) == e, User.activo.is_(True)).limit(1))
    return u


def crear_token(app: Any, tipo: str, obj_id: int, *, email: str = "", user_id: int | None = None, **extra: Any) -> str:
    if tipo not in TIPOS:
        raise ValueError(f"tipo de acción desconocido: {tipo}")
    if user_id is None and email:
        u = usuario_por_email(email)
        user_id = int(u.id) if u is not None else None
    data: dict[str, Any] = {"t": tipo, "id": int(obj_id), "e": (email or "").strip().lower()[:254]}
    if user_id is not None:
        data["u"] = int(user_id)
    data.update(extra)
    return _serializer(app).dumps(data)


def url(app: Any, tipo: str, obj_id: int, *, email: str = "", user_id: int | None = None, **extra: Any) -> str:
    from app.services.mail_link_service import public_abs_url

    return public_abs_url(app, "accion.ver", token=crear_token(app, tipo, obj_id, email=email, user_id=user_id, **extra))


def leer_token(token: str) -> tuple[dict[str, Any] | None, str]:
    """(datos, error). Los datos traen además `user` (User o None)."""
    try:
        data = _serializer().loads(token, max_age=VIGENCIA_DIAS * 86400)
    except SignatureExpired:
        return None, "El link venció. Entrá al sistema o pedí que te reenvíen el aviso."
    except BadSignature:
        return None, "El link no es válido."
    if not isinstance(data, dict) or data.get("t") not in TIPOS:
        return None, "El link no es válido."
    user = None
    if data.get("u"):
        user = db.session.get(User, int(data["u"]))
        if user is not None and not user.activo:
            return None, "Tu usuario está inactivo."
    data["user"] = user
    return data, ""


def actor_label(data: dict[str, Any]) -> str:
    from app.auth_utils import user_display_name

    user = data.get("user")
    return (user_display_name(user) if user is not None else "") or data.get("e") or "link del aviso"


def registrar(data: dict[str, Any], accion: str, entity_type: str, entity_id: int | None, detalle: str = "") -> None:
    from app.services import security_audit_service as audit_svc

    user = data.get("user")
    audit_svc.record_event(
        action=f"accion_link_{accion}",
        module="avisos",
        actor=user,
        actor_username=None if user is not None else (data.get("e") or None),
        entity_type=entity_type,
        entity_id=entity_id,
        detail=(f"{detalle} (desde el link del aviso)").strip(),
    )
