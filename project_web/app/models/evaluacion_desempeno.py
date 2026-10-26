from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluacionDesempeno(db.Model):
    """Una evaluación de desempeño (registro SGI QDV-RG-PG-05_04)."""

    __tablename__ = "evaluaciones_desempeno"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    # Legajo del evaluado, si el nombre coincide con uno de Personal.
    empleado_id = db.Column(
        db.Integer, db.ForeignKey("personal_empleados.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sector = db.Column(db.String(128), nullable=False, default="", server_default="")
    puesto = db.Column(db.String(128), nullable=False, default="", server_default="")
    evaluado = db.Column(db.String(255), nullable=False, default="", server_default="")
    periodo = db.Column(db.String(80), nullable=False, default="", server_default="")
    evaluador = db.Column(db.String(255), nullable=False, default="", server_default="")
    fecha = db.Column(db.Date, nullable=True)
    # JSON {"<n° de ítem>": 1..5}
    puntajes = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    comentarios_evaluador = db.Column(db.Text, nullable=False, default="", server_default="")
    comentarios_evaluado = db.Column(db.Text, nullable=False, default="", server_default="")
    observaciones = db.Column(db.Text, nullable=False, default="", server_default="")  # uno por renglón
    objetivos = db.Column(db.Text, nullable=False, default="", server_default="")  # uno por renglón
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class EvaluacionDesempenoCambio(db.Model):
    __tablename__ = "evaluaciones_desempeno_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    evaluacion_id = db.Column(
        db.Integer, db.ForeignKey("evaluaciones_desempeno.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
