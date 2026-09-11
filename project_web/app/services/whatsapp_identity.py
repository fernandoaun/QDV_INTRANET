"""Normaliza y resuelve el número de WhatsApp al usuario QDV."""

from __future__ import annotations

import re

from sqlalchemy import select

from app.extensions import db
from app.models import EmpleadoPersonal, User
from app.user_roles import ROLE_LABORATORISTA, normalize_stored_rol


def normalize_whatsapp_e164(raw: str | None) -> str:
    """Devuelve E.164 (+54911…) o cadena vacía si no se puede interpretar."""
    s = (raw or "").strip()
    if not s:
        return ""
    lower = s.lower()
    if lower.startswith("whatsapp:"):
        s = s.split(":", 1)[1]
    if "@" in s:
        s = s.split("@", 1)[0]
    s = s.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("+"):
        digits = "+" + re.sub(r"\D", "", s[1:])
    else:
        digits = re.sub(r"\D", "", s)
        if digits.startswith("54"):
            digits = "+" + digits
        elif digits.startswith("9") and len(digits) == 10:
            digits = "+54" + digits
        elif 8 <= len(digits) <= 15:
            digits = "+" + digits
        else:
            return ""
    body = digits[1:]
    if not (8 <= len(body) <= 15) or not body.isdigit():
        return ""
    return digits


def find_user_by_whatsapp(raw: str | None) -> User | None:
    e164 = normalize_whatsapp_e164(raw)
    if not e164:
        return None
    user = db.session.scalar(select(User).where(User.whatsapp_e164 == e164))
    if user is not None:
        return user
    empleados = db.session.scalars(select(EmpleadoPersonal).where(EmpleadoPersonal.user_id.is_not(None))).all()
    for emp in empleados:
        if normalize_whatsapp_e164(emp.telefono) == e164 and emp.user_id:
            found = db.session.get(User, int(emp.user_id))
            if found is not None:
                return found
    return None


def whatsapp_user_blocked_reason(user: User | None) -> str | None:
    if user is None:
        return "No hay un usuario QDV con ese número de WhatsApp."
    if not user.activo:
        return "El usuario está inactivo."
    if normalize_stored_rol(getattr(user, "rol", None)) == ROLE_LABORATORISTA:
        return "El perfil laboratorista no opera el sistema por su cuenta; en planta acompaña al operador."
    return None
