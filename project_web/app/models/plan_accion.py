from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlanAccion(db.Model):
    """Una acción del Plan de acción (registro SGI QDV-RG-PG-02_03)."""

    __tablename__ = "plan_accion"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    # Identificación y trazabilidad
    origen = db.Column(db.String(80), nullable=False, default="", server_default="")
    tipo_hallazgo = db.Column(db.String(80), nullable=False, default="", server_default="")
    fecha_deteccion = db.Column(db.Date, nullable=True)
    # Análisis
    tipo_accion = db.Column(db.String(80), nullable=False, default="", server_default="")
    accion = db.Column(db.Text, nullable=False, default="", server_default="")
    causa_raiz = db.Column(db.String(20), nullable=False, default="", server_default="")
    causa_raiz_descripcion = db.Column(db.Text, nullable=False, default="", server_default="")
    # Planificación
    requisito = db.Column(db.String(255), nullable=False, default="", server_default="")
    fecha_cumplimiento = db.Column(db.Date, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default="", server_default="")
    responsable = db.Column(db.String(255), nullable=False, default="", server_default="")
    # Seguimiento
    metodo_eficacia = db.Column(db.Text, nullable=False, default="", server_default="")
    resultado_eficacia = db.Column(db.String(20), nullable=False, default="", server_default="")
    comentarios = db.Column(db.Text, nullable=False, default="", server_default="")
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class PlanAccionCambio(db.Model):
    __tablename__ = "plan_accion_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    accion_id = db.Column(db.Integer, db.ForeignKey("plan_accion.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
