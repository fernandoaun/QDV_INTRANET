from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SectorVencimiento(db.Model):
    __tablename__ = "sectores_vencimientos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(128), nullable=False, index=True)
    descripcion = db.Column(db.String(512), nullable=False, default="", server_default="")
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)


class Vencimiento(db.Model):
    __tablename__ = "vencimientos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sector_id = db.Column(
        db.Integer, db.ForeignKey("sectores_vencimientos.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    nombre = db.Column(db.String(256), nullable=False, index=True)
    descripcion = db.Column(db.String(4000), nullable=False, default="", server_default="")
    fecha_vencimiento = db.Column(db.Date, nullable=False, index=True)
    responsable = db.Column(db.String(256), nullable=False, default="", server_default="")
    email_aviso = db.Column(db.String(256), nullable=False, default="", server_default="")
    estado = db.Column(db.String(32), nullable=False, default="vigente", server_default="vigente")
    observaciones = db.Column(db.String(4000), nullable=False, default="", server_default="")
    archivo_path = db.Column(db.String(512), nullable=True)
    aviso_30_dias_enviado = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    fecha_aviso_30_dias = db.Column(db.DateTime(timezone=True), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    continuacion_de_id = db.Column(db.Integer, db.ForeignKey("vencimientos.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)

    sector = db.relationship("SectorVencimiento", backref=db.backref("vencimientos", lazy="dynamic"))


class VencimientoHistorial(db.Model):
    __tablename__ = "vencimientos_historial"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    vencimiento_id = db.Column(db.Integer, db.ForeignKey("vencimientos.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    usuario = db.Column(db.String(256), nullable=False, default="", server_default="")
    accion = db.Column(db.String(64), nullable=False, index=True)
    detalle = db.Column(db.String(8000), nullable=False, default="", server_default="")
