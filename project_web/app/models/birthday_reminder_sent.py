from __future__ import annotations

from datetime import date, datetime, timezone

from app.extensions import db

KIND_CONGRATS = "congrats"
KIND_TEAM = "team"
TEAM_ENTITY_ID = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BirthdayReminderSent(db.Model):
    """Evita reenviar avisos de cumpleaños el mismo día (compartido entre cron y web)."""

    __tablename__ = "birthday_reminders_sent"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    operacion_date = db.Column(db.Date, nullable=False, index=True)
    kind = db.Column(db.String(16), nullable=False, index=True)
    empleado_id = db.Column(db.Integer, nullable=False, default=TEAM_ENTITY_ID, server_default="0")
    sent_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "operacion_date",
            "kind",
            "empleado_id",
            name="uq_birthday_reminder_date_kind_empleado",
        ),
    )
