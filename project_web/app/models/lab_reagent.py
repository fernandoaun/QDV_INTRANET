from __future__ import annotations

from app.extensions import db


class LaboratoryReagent(db.Model):
    """Catálogo de reactivos de laboratorio con ficha PDF."""

    __tablename__ = "laboratory_reagents"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(256), nullable=False, index=True)
    pdf_stored_filename = db.Column(db.String(256), nullable=False)
    pdf_original_filename = db.Column(db.String(256), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    created_by = db.relationship("User", foreign_keys=[created_by_user_id])


class LaboratoryReagentUsage(db.Model):
    """Registro de uso/consumo de un reactivo (trazabilidad)."""

    __tablename__ = "laboratory_reagent_usages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reagent_id = db.Column(
        db.Integer, db.ForeignKey("laboratory_reagents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(64), nullable=False)
    used_at_iso = db.Column(db.String(32), nullable=False, index=True)
    registered_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False, index=True)
    operator_display_name = db.Column(db.String(512), nullable=False)
    shift_session_id = db.Column(
        db.Integer, db.ForeignKey("shift_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes = db.Column(db.Text, nullable=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    reagent = db.relationship("LaboratoryReagent", foreign_keys=[reagent_id])
    registered_by = db.relationship("User", foreign_keys=[registered_by_user_id])
    shift_session = db.relationship("ShiftSession", foreign_keys=[shift_session_id])
