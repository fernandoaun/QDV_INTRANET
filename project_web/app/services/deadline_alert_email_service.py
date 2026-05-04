from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import DeadlineAlertEmail

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_validate_email(raw: str | None) -> str | None:
    s = (raw or "").strip().lower()
    if not s or len(s) > 254:
        return None
    if not _EMAIL_RE.match(s):
        return None
    return s


def list_emails_ordered() -> list[DeadlineAlertEmail]:
    return list(db.session.scalars(select(DeadlineAlertEmail).order_by(DeadlineAlertEmail.email)).all())


def merged_recipient_addresses(app: Any) -> list[str]:
    """Unión de correos en BD y variable DEADLINE_ALERT_EMAIL_TO (sin duplicados)."""
    db_addrs = [str(r.email).strip().lower() for r in list_emails_ordered()]
    env_addrs = [str(e).strip().lower() for e in (app.config.get("DEADLINE_ALERT_EMAIL_TO") or []) if str(e).strip()]
    return sorted(set(db_addrs + env_addrs))


def add_email(raw: str | None) -> tuple[bool, str]:
    """Devuelve (ok, mensaje)."""
    norm = normalize_validate_email(raw)
    if norm is None:
        return False, "Ingresá un correo electrónico válido."

    exists = db.session.scalar(select(DeadlineAlertEmail.id).where(DeadlineAlertEmail.email == norm))
    if exists is not None:
        return False, "Ese correo ya está en la lista."

    db.session.add(DeadlineAlertEmail(email=norm))
    db.session.commit()
    return True, "Correo agregado."


def delete_email_row(row_id: int) -> str | None:
    row = db.session.get(DeadlineAlertEmail, int(row_id))
    if row is None:
        return None
    em = row.email
    db.session.delete(row)
    db.session.commit()
    return em
