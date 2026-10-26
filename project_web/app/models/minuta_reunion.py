from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MinutaReunion(db.Model):
    """Una minuta de reunión (registro SGI QDV-RG-PG-04_01)."""

    __tablename__ = "minutas_reunion"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=True)
    horario = db.Column(db.String(60), nullable=False, default="", server_default="")
    lugar = db.Column(db.String(255), nullable=False, default="", server_default="")
    motivo = db.Column(db.Text, nullable=False, default="", server_default="")
    # JSON [{participante, sector, asistencia (Presente / Ausente)}]
    participantes = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    desarrollo = db.Column(db.Text, nullable=False, default="", server_default="")
    # JSON [{accion, responsable, fecha (dd/mm/aaaa)}]
    acciones = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class MinutaReunionCambio(db.Model):
    __tablename__ = "minutas_reunion_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    minuta_id = db.Column(db.Integer, db.ForeignKey("minutas_reunion.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
