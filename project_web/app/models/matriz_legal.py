from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RequisitoLegal(db.Model):
    """Un requisito de la Matriz legal y otros requisitos (registro SGI QDV-RG-PG-10_01)."""

    __tablename__ = "matriz_legal"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ambito = db.Column(db.String(20), nullable=False, index=True)  # nacion | rn | otros (hojas de la planilla)
    tipo = db.Column(db.String(80), nullable=False, default="", server_default="")
    fuente = db.Column(db.String(160), nullable=False, default="", server_default="")
    organismo = db.Column(db.String(160), nullable=False, default="", server_default="")
    norma = db.Column(db.String(255), nullable=False, default="", server_default="")
    articulo = db.Column(db.String(160), nullable=False, default="", server_default="")
    descripcion = db.Column(db.Text, nullable=False, default="", server_default="")
    proceso = db.Column(db.String(160), nullable=False, default="", server_default="")
    responsable = db.Column(db.String(160), nullable=False, default="", server_default="")
    evidencia = db.Column(db.Text, nullable=False, default="", server_default="")
    frecuencia = db.Column(db.String(80), nullable=False, default="", server_default="")
    estado = db.Column(db.String(40), nullable=False, default="", server_default="")
    observaciones = db.Column(db.Text, nullable=False, default="", server_default="")
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class RequisitoLegalCambio(db.Model):
    __tablename__ = "matriz_legal_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    requisito_id = db.Column(db.Integer, db.ForeignKey("matriz_legal.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
