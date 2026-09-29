from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FichaProceso(db.Model):
    """Ficha de proceso (tortuga) del registro SGI QDV-RG-PG-09_03. Listas: un ítem por renglón."""

    __tablename__ = "fichas_proceso"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    proceso = db.Column(db.String(160), nullable=False)
    responsable = db.Column(db.String(160), nullable=False, default="", server_default="")
    actividades = db.Column(db.Text, nullable=False, default="", server_default="")
    entradas = db.Column(db.Text, nullable=False, default="", server_default="")
    salidas = db.Column(db.Text, nullable=False, default="", server_default="")
    como = db.Column(db.Text, nullable=False, default="", server_default="")
    con_que = db.Column(db.Text, nullable=False, default="", server_default="")
    con_quien = db.Column(db.Text, nullable=False, default="", server_default="")
    indicadores = db.Column(db.Text, nullable=False, default="", server_default="")
    fecha_actualizacion = db.Column(db.Date, nullable=True)
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class FichaProcesoCambio(db.Model):
    __tablename__ = "fichas_proceso_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ficha_id = db.Column(db.Integer, db.ForeignKey("fichas_proceso.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
