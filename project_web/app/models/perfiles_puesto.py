from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PerfilPuesto(db.Model):
    """Perfil de puesto del registro SGI QDV-RG-PG-05_01. Listas: un ítem por renglón."""

    __tablename__ = "perfiles_puesto"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    puesto = db.Column(db.String(160), nullable=False)
    proceso = db.Column(db.String(160), nullable=False, default="", server_default="")
    supervisor = db.Column(db.String(160), nullable=False, default="", server_default="")
    supervisa_a = db.Column(db.Text, nullable=False, default="", server_default="")
    interactua_con = db.Column(db.Text, nullable=False, default="", server_default="")
    tareas = db.Column(db.Text, nullable=False, default="", server_default="")
    educacion = db.Column(db.Text, nullable=False, default="", server_default="")
    formacion = db.Column(db.Text, nullable=False, default="", server_default="")
    idiomas_otros = db.Column(db.Text, nullable=False, default="", server_default="")
    experiencia = db.Column(db.Text, nullable=False, default="", server_default="")
    habilidades = db.Column(db.Text, nullable=False, default="", server_default="")
    autoridad = db.Column(db.Text, nullable=False, default="", server_default="")
    rendicion_cuentas = db.Column(db.Text, nullable=False, default="", server_default="")
    aprobado_por = db.Column(db.String(160), nullable=False, default="", server_default="")
    fecha_actualizacion = db.Column(db.Date, nullable=True)
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class PerfilPuestoCambio(db.Model):
    __tablename__ = "perfiles_puesto_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    perfil_id = db.Column(db.Integer, db.ForeignKey("perfiles_puesto.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
