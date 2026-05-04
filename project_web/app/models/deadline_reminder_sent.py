from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DeadlineReminderSent(db.Model):
    """Evita reenviar el mismo aviso de plazo (planificación / orden de mantenimiento)."""

    __tablename__ = "deadline_reminders_sent"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    domain = db.Column(db.String(32), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (db.UniqueConstraint("domain", "entity_id", name="uq_deadline_reminder_domain_entity"),)
