"""Normaliza y resuelve el número de WhatsApp al usuario QDV."""

from __future__ import annotations

import re

from sqlalchemy import select

from app.extensions import db
from app.models import EmpleadoPersonal, User
from app.user_roles import ROLE_LABORATORISTA, normalize_stored_rol


def _ar_nacional(digits: str) -> str:
    """Número argentino sin 54/9 ni 0 de larga distancia -> 10 dígitos (área + abonado), o ''.

    Saca el 15 de celular cargado a la vieja ("3834 15-123456" -> "3834123456").
    """
    d = digits.lstrip("0")
    if len(d) == 12:
        for area in (2, 3, 4):
            if d[area : area + 2] == "15":
                d = d[:area] + d[area + 2 :]
                break
    return d if len(d) == 10 else ""


def normalize_whatsapp_e164(raw: str | None) -> str:
    """Devuelve E.164 (+54911…) o cadena vacía si no se puede interpretar.

    Los celulares argentinos quedan como los manda WhatsApp: +549 + área + abonado.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    lower = s.lower()
    if lower.startswith("whatsapp:"):
        s = s.split(":", 1)[1]
    if "@" in s:
        s = s.split("@", 1)[0]
    s = s.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace(".", "")
    internacional = s.startswith("+") or s.startswith("00")
    digits = re.sub(r"\D", "", s[2:] if s.startswith("00") else s)
    if internacional or (digits.startswith("54") and len(digits) >= 12):
        if digits.startswith("54"):
            resto = digits[2:]
            if resto.startswith("9"):
                resto = resto[1:]
            nacional = _ar_nacional(resto)
            return "+549" + nacional if nacional else ""
        return "+" + digits if 8 <= len(digits) <= 15 else ""
    nacional = _ar_nacional(digits)
    if nacional:
        return "+549" + nacional
    if digits.startswith("9") and len(digits) == 11:
        return "+54" + digits
    return ""


def find_user_by_whatsapp(raw: str | None) -> User | None:
    e164 = normalize_whatsapp_e164(raw)
    if not e164:
        return None
    user = db.session.scalar(select(User).where(User.whatsapp_e164 == e164))
    if user is not None:
        return user
    # Números guardados con otra normalización (p. ej. +54 sin el 9 de celular).
    for u in db.session.scalars(select(User).where(User.whatsapp_e164.is_not(None))).all():
        if normalize_whatsapp_e164(u.whatsapp_e164) == e164:
            return u
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
