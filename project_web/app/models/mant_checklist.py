from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MantChecklist(db.Model):
    """Checklist de inspección de un equipo (registro del PO-01, p. ej. QDV-RG-PO-01_07 Compresor de aire)."""

    __tablename__ = "mant_checklists"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=False, unique=True)
    codigo = db.Column(db.String(64), nullable=False, default="", server_default="")
    titulo = db.Column(db.String(255), nullable=False, default="", server_default="")
    # JSON [ítem, …]: lo que se inspecciona, en el orden del formulario.
    items = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    equipo = db.relationship("Equipo", lazy="joined")


class MantChecklistRegistro(db.Model):
    """Un checklist realizado: respuesta por ítem y firmas en el sistema del inspector y del Responsable de Planta."""

    __tablename__ = "mant_checklist_registros"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    checklist_id = db.Column(db.Integer, db.ForeignKey("mant_checklists.id"), nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.Date, nullable=False, index=True)
    area = db.Column(db.String(255), nullable=False, default="", server_default="")
    actividad = db.Column(db.Text, nullable=False, default="", server_default="")
    # JSON [{item, estado (Buen estado / Mal estado)}]: copia de los ítems al momento de la inspección.
    respuestas = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    observaciones = db.Column(db.Text, nullable=False, default="", server_default="")
    inspector_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    inspector_nombre = db.Column(db.String(255), nullable=False, default="", server_default="")
    inspector_firma_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    planta_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    planta_nombre = db.Column(db.String(255), nullable=False, default="", server_default="")
    planta_firma_at = db.Column(db.DateTime(timezone=True), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)

    checklist = db.relationship("MantChecklist", lazy="joined")
