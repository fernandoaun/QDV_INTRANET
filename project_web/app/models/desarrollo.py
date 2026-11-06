from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DesarrolloProduccion(db.Model):
    """Diseño y desarrollo de producción (QDV-PO-03): registros QDV-RG-PO-03_01 a 03_03 de un desarrollo."""

    __tablename__ = "desarrollos_produccion"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    fecha_inicio = db.Column(db.Date, nullable=False)
    producto_proceso = db.Column(db.String(255), nullable=False, default="", server_default="")
    tipo = db.Column(db.String(32), nullable=False, default="", server_default="")
    motivo = db.Column(db.Text, nullable=False, default="", server_default="")
    # Período de pruebas: de ahí sale la evidencia del sistema (laboratorio, proceso, insumos, lotes).
    prueba_desde = db.Column(db.Date, nullable=False)
    prueba_hasta = db.Column(db.Date, nullable=True)
    # JSON con lo que se completa a mano en cada hoja (planificación, entradas, salidas, revisión, validación…).
    datos = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    # JSON {planta|calidad|gerencia: {user_id, nombre, at}}: firmas en el sistema.
    firmas = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class DesarrolloCambio(db.Model):
    """Cambio de diseño y desarrollo (QDV-RG-PO-03_04)."""

    __tablename__ = "desarrollos_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    desarrollo_id = db.Column(db.Integer, db.ForeignKey("desarrollos_produccion.id"), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False)
    datos = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    firmas = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    desarrollo = db.relationship("DesarrolloProduccion", lazy="joined")


class DesarrolloHistorial(db.Model):
    __tablename__ = "desarrollos_historial"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    desarrollo_id = db.Column(db.Integer, db.ForeignKey("desarrollos_produccion.id", ondelete="CASCADE"), nullable=False, index=True)
    cambio_id = db.Column(db.Integer, db.ForeignKey("desarrollos_cambios.id", ondelete="SET NULL"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    detalle = db.Column(db.Text, nullable=False, default="", server_default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
