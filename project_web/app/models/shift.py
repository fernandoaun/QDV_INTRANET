"""Sesión operativa de planta y entrega/recepción de turno (perfil operaciones / mantenimiento y operaciones)."""
from __future__ import annotations

from app.extensions import db


class ShiftSession(db.Model):
    __tablename__ = "shift_sessions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False, index=True)
    laboratorist_user_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    effective_role = db.Column(db.String(32), nullable=False)
    started_at_iso = db.Column(db.String(32), nullable=False)
    ended_at_iso = db.Column(db.String(32), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="open", index=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    user = db.relationship("User", foreign_keys=[user_id])
    laboratorist_user = db.relationship("User", foreign_keys=[laboratorist_user_id])


class ShiftHandover(db.Model):
    __tablename__ = "shift_handovers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    shift_session_id = db.Column(
        db.Integer, db.ForeignKey("shift_sessions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    outgoing_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    incoming_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True)

    shift_started_at_iso = db.Column(db.String(32), nullable=False)
    handed_over_at_iso = db.Column(db.String(32), nullable=False)
    received_at_iso = db.Column(db.String(32), nullable=True)

    hypochlorite_stock_liters = db.Column(db.Float, nullable=False)
    closing_notes = db.Column(db.Text, nullable=True)

    reception_status = db.Column(db.String(64), nullable=True)
    reception_notes = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(32), nullable=False, default="pending_reception", index=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    shift_session = db.relationship("ShiftSession", foreign_keys=[shift_session_id])
    outgoing_user = db.relationship("User", foreign_keys=[outgoing_user_id])
    incoming_user = db.relationship("User", foreign_keys=[incoming_user_id])
    warning_actions = db.relationship(
        "ShiftHandoverWarningAction",
        backref="handover",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class ShiftHandoverWarningAction(db.Model):
    __tablename__ = "shift_handover_warning_actions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    handover_id = db.Column(db.Integer, db.ForeignKey("shift_handovers.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = db.Column(db.String(32), nullable=False)
    source_record_id = db.Column(db.Integer, nullable=False)
    warning_code = db.Column(db.String(128), nullable=False)
    warning_message = db.Column(db.Text, nullable=False)
    action_taken = db.Column(db.Text, nullable=False)
    created_at_iso = db.Column(db.String(32), nullable=False)
    # Trazabilidad del registro que originó el aviso (denormalizado al entregar turno)
    record_created_at_iso = db.Column(db.String(64), nullable=True)
    origin_display = db.Column(db.String(128), nullable=True)
