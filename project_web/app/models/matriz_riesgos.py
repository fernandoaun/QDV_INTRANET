from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MatrizRiesgos(db.Model):
    """Matriz de riesgos y oportunidades de un sector (registro SGI QDV-RG-PG-09_04, una hoja por sector)."""

    __tablename__ = "matriz_riesgos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sector = db.Column(db.String(160), nullable=False, index=True)
    # Se pone sola cada vez que cambia la hoja.
    fecha_actualizacion = db.Column(db.Date, nullable=True)
    # JSON [{tipo, riesgo, probabilidad, severidad, acciones, fecha (mm/aaaa o dd/mm/aaaa), responsables, eficacia}]
    filas = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class MatrizRiesgosCambio(db.Model):
    __tablename__ = "matriz_riesgos_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    matriz_id = db.Column(db.Integer, db.ForeignKey("matriz_riesgos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
