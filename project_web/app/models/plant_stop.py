"""Paradas de planta: pausa de cronómetros de análisis y aviso por correo."""
from __future__ import annotations

from app.extensions import db


class PlantStopAlertEmail(db.Model):
    """Destinatario de avisos de parada (solo administración; oculto al operador)."""

    __tablename__ = "plant_stop_alert_emails"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(256), nullable=False, unique=True, index=True)


class PlantStopEvent(db.Model):
    """Declaración de parada de planta en un circuito / electrolizador."""

    __tablename__ = "plant_stop_events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    circuit_key = db.Column(db.String(32), nullable=False, index=True)
    started_at_iso = db.Column(db.String(32), nullable=False, index=True)
    ended_at_iso = db.Column(db.String(32), nullable=True, index=True)
    operador = db.Column(db.String(256), nullable=False, default="")
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    observaciones = db.Column(db.Text, nullable=True)
    frozen_remaining_sec = db.Column(db.Integer, nullable=True)
    frozen_remaining_sec_analisis8 = db.Column(db.Integer, nullable=True)
    mail_sent_at_iso = db.Column(db.String(32), nullable=True)
    created_at_iso = db.Column(db.String(32), nullable=False)

    user = db.relationship("User", foreign_keys=[user_id])
