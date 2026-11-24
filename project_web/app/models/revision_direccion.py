from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RevisionDireccion(db.Model):
    """Una minuta de revisión por la dirección (registro SGI QDV-RG-PG-07_01)."""

    __tablename__ = "revisiones_direccion"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=True)
    # JSON {"<clave del tema>": "lo tratado"}: los temas de entrada de la revisión (ISO 9001/14001/45001, 9.3.2).
    temas = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    # JSON [{participante, cargo, user_id, firma_at, firma_via}]
    participantes = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    # JSON [{accion, responsable, fecha (dd/mm/aaaa), plan_accion_id}]: decisiones y acciones (salidas, 9.3.3).
    acciones = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class RevisionDireccionCambio(db.Model):
    __tablename__ = "revisiones_direccion_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    revision_id = db.Column(
        db.Integer, db.ForeignKey("revisiones_direccion.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
