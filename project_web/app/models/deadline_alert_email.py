from __future__ import annotations

from app.extensions import db


class DeadlineAlertEmail(db.Model):
    """Destinatarios configurados en panel para avisos de planificación / mantenimiento."""

    __tablename__ = "deadline_alert_emails"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(256), nullable=False, unique=True, index=True)
