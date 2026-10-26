from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Foda(db.Model):
    """FODA de la empresa (registro SGI QDV-RG-PG-09_01). Una sola fila; listas: un ítem por renglón."""

    __tablename__ = "foda"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fortalezas = db.Column(db.Text, nullable=False, default="", server_default="")
    oportunidades = db.Column(db.Text, nullable=False, default="", server_default="")
    debilidades = db.Column(db.Text, nullable=False, default="", server_default="")
    amenazas = db.Column(db.Text, nullable=False, default="", server_default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class FodaCambio(db.Model):
    __tablename__ = "foda_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    foda_id = db.Column(db.Integer, db.ForeignKey("foda.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
