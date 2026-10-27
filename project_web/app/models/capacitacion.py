from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Capacitacion(db.Model):
    """Un registro de capacitación (registro SGI QDV-RG-PG-05_03)."""

    __tablename__ = "capacitaciones"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=True)
    lugar = db.Column(db.String(255), nullable=False, default="", server_default="")
    duracion = db.Column(db.String(60), nullable=False, default="", server_default="")
    disertantes = db.Column(db.String(255), nullable=False, default="", server_default="")
    tema = db.Column(db.Text, nullable=False, default="", server_default="")
    material = db.Column(db.Text, nullable=False, default="", server_default="")
    # JSON {"<clave del método>": {"marcado": bool, "detalle", "responsable", "plazo"}}
    metodos = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    # JSON [{"nombre", "sector", "empleado_id"}]; empleado_id si el nombre coincide con un legajo de Personal.
    asistentes = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    eficaz = db.Column(db.String(2), nullable=False, default="", server_default="")  # SI / NO / ""
    nuevas_acciones = db.Column(db.String(2), nullable=False, default="", server_default="")  # SI / NO / ""
    nuevas_acciones_detalle = db.Column(db.Text, nullable=False, default="", server_default="")
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class CapacitacionCambio(db.Model):
    __tablename__ = "capacitaciones_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    capacitacion_id = db.Column(
        db.Integer, db.ForeignKey("capacitaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
