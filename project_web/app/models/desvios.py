from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Desvio(db.Model):
    """Un reporte de No conformidad, PNC u Oportunidad de mejora (registro SGI QDV-RG-PG-08_01).

    El listado de reportes es el Seguimiento de PNC, NC y OM (QDV-RG-PG-08_02).
    """

    __tablename__ = "desvios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=True)
    clasificacion = db.Column(db.String(30), nullable=False, default="", server_default="")
    fuentes = db.Column(db.Text, nullable=False, default="", server_default="")  # una por renglón
    descripcion = db.Column(db.Text, nullable=False, default="", server_default="")
    emisor = db.Column(db.String(255), nullable=False, default="", server_default="")
    encuadre = db.Column(db.Text, nullable=False, default="", server_default="")  # uno por renglón
    requisito = db.Column(db.Text, nullable=False, default="", server_default="")
    causa_raiz = db.Column(db.Text, nullable=False, default="", server_default="")
    # JSON [{detalle, responsable, fecha (dd/mm/aaaa), plan_accion_id?}]
    acciones_inmediatas = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    correcciones = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    acciones_correctivas = db.Column(db.Text, nullable=False, default="[]", server_default="[]")
    evidencia = db.Column(db.Text, nullable=False, default="", server_default="")
    verificador = db.Column(db.String(255), nullable=False, default="", server_default="")
    implementadas = db.Column(db.String(2), nullable=False, default="", server_default="")
    fecha_implementacion = db.Column(db.Date, nullable=True)
    eficaces = db.Column(db.String(2), nullable=False, default="", server_default="")
    fecha_eficacia = db.Column(db.Date, nullable=True)
    cierre_responsables = db.Column(db.Text, nullable=False, default="", server_default="")  # uno por renglón
    fecha_cierre = db.Column(db.Date, nullable=True)
    estado = db.Column(db.String(30), nullable=False, default="Abierta", server_default="Abierta")
    # Baja lógica: deja de listarse pero conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class DesvioCambio(db.Model):
    __tablename__ = "desvios_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    desvio_id = db.Column(db.Integer, db.ForeignKey("desvios.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(32), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
