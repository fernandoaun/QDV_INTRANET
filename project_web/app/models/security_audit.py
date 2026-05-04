"""Registros de auditoría para trazabilidad y respuesta ante incidentes (no sustituye logs de servidor)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SecurityAuditLog(db.Model):
    __tablename__ = "security_audit_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_username = db.Column(db.String(128), nullable=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    module = db.Column(db.String(64), nullable=False, default="general", index=True)
    entity_type = db.Column(db.String(64), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
    old_value = db.Column(db.Text(), nullable=True)
    new_value = db.Column(db.Text(), nullable=True)
    detail = db.Column(db.Text(), nullable=True)
