from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SolicitudCambio(db.Model):
    """Una solicitud de cambio (registro SGI QDV-RG-PG-03_01)."""

    __tablename__ = "solicitudes_cambio"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    # Sección 1: solicitud del cambio
    fecha = db.Column(db.Date, nullable=True)
    asunto = db.Column(db.String(255), nullable=False, default="", server_default="")
    solicita = db.Column(db.String(255), nullable=False, default="", server_default="")
    estado = db.Column(db.String(40), nullable=False, default="", server_default="")
    sector = db.Column(db.String(255), nullable=False, default="", server_default="")
    requerido_para = db.Column(db.Date, nullable=True)
    razon = db.Column(db.Text, nullable=False, default="", server_default="")
    prioridad = db.Column(db.String(20), nullable=False, default="", server_default="")
    descripcion = db.Column(db.Text, nullable=False, default="", server_default="")
    tipos = db.Column(db.Text, nullable=False, default="", server_default="")  # uno por renglón
    # Sección 2: evaluación del cambio
    fecha_evaluacion = db.Column(db.Date, nullable=True)
    equipo_evaluacion = db.Column(db.Text, nullable=False, default="", server_default="")
    impactos = db.Column(db.Text, nullable=False, default="", server_default="")
    # Sección 3: resolución
    resolucion = db.Column(db.String(20), nullable=False, default="", server_default="")
    fecha_resolucion = db.Column(db.Date, nullable=True)
    # Acciones de control: JSON [{actividad, responsable, fecha (dd/mm/aaaa), eficacia}]
    acciones_control = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class SolicitudCambioCambio(db.Model):
    __tablename__ = "solicitudes_cambio_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    solicitud_id = db.Column(
        db.Integer, db.ForeignKey("solicitudes_cambio.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
