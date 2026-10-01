from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AppParametro(db.Model):
    """Parámetro operativo editable por el administrador (clave → valor de texto)."""

    __tablename__ = "app_parametros"

    clave = db.Column(db.String(64), primary_key=True)
    valor = db.Column(db.String(256), nullable=False, default="", server_default="")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
