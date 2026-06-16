from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import StockAlertEmail
from app.services.deadline_alert_email_service import normalize_validate_email

__all__ = [
    "add_email",
    "delete_email_row",
    "list_emails_ordered",
    "merged_recipient_addresses",
    "normalize_validate_email",
]


def list_emails_ordered() -> list[StockAlertEmail]:
    return list(db.session.scalars(select(StockAlertEmail).order_by(StockAlertEmail.email)).all())


def merged_recipient_addresses(app: Any) -> list[str]:
    """Unión de correos en BD y variable STOCK_CRITICAL_ALERT_EMAIL_TO (sin duplicados)."""
    db_addrs = [str(r.email).strip().lower() for r in list_emails_ordered()]
    env_addrs = [
        str(e).strip().lower()
        for e in (app.config.get("STOCK_CRITICAL_ALERT_EMAIL_TO") or [])
        if str(e).strip()
    ]
    return sorted(set(db_addrs + env_addrs))


def add_email(raw: str | None) -> tuple[bool, str]:
    norm = normalize_validate_email(raw)
    if norm is None:
        return False, "Ingresá un correo electrónico válido."

    exists = db.session.scalar(select(StockAlertEmail.id).where(StockAlertEmail.email == norm))
    if exists is not None:
        return False, "Ese correo ya está en la lista."

    db.session.add(StockAlertEmail(email=norm))
    db.session.commit()
    return True, "Correo agregado."


def delete_email_row(row_id: int) -> str | None:
    row = db.session.get(StockAlertEmail, int(row_id))
    if row is None:
        return None
    em = row.email
    db.session.delete(row)
    db.session.commit()
    return em
