"""Modelos del módulo SGI – Sistema de Gestión Integrado.

Estructura preparada para ampliar con: difusión documental, lecturas por usuario,
organigrama, control de cambios, matriz documental, documentos externos y vencimientos.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Tipos de documento SGI
TIPO_PG = "PG"
TIPO_PO = "PO"
TIPO_MSGI = "MSGI"

TIPOS_DOCUMENTO: tuple[str, ...] = (TIPO_PG, TIPO_PO, TIPO_MSGI)

TIPO_SLUGS: dict[str, str] = {
    TIPO_PG: "pg",
    TIPO_PO: "po",
    TIPO_MSGI: "msgi",
}

SLUG_TO_TIPO: dict[str, str] = {v: k for k, v in TIPO_SLUGS.items()}

TIPO_LABELS: dict[str, str] = {
    TIPO_PG: "PG – Procedimientos de Gestión",
    TIPO_PO: "PO – Procedimientos Operativos",
    TIPO_MSGI: "MSGI – Manual del Sistema de Gestión Integrado",
}

ESTADO_BORRADOR = "borrador"
ESTADO_VIGENTE = "vigente"
ESTADO_OBSOLETO = "obsoleto"

ESTADOS_DOCUMENTO: tuple[str, ...] = (ESTADO_BORRADOR, ESTADO_VIGENTE, ESTADO_OBSOLETO)

ESTADO_LABELS: dict[str, str] = {
    ESTADO_BORRADOR: "Borrador",
    ESTADO_VIGENTE: "Vigente",
    ESTADO_OBSOLETO: "Obsoleto",
}


class SgiDocumento(db.Model):
    __tablename__ = "sgi_documentos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tipo = db.Column(db.String(8), nullable=False, index=True)
    codigo = db.Column(db.String(64), nullable=False, index=True)
    titulo = db.Column(db.String(512), nullable=False, index=True)
    revision = db.Column(db.String(32), nullable=False, default="", server_default="")
    fecha_creacion_doc = db.Column(db.Date, nullable=True, index=True)
    fecha_ultima_revision = db.Column(db.Date, nullable=True, index=True)
    responsable_elaboracion = db.Column(db.String(256), nullable=False, default="", server_default="")
    responsable_aprobacion = db.Column(db.String(256), nullable=False, default="", server_default="")
    estado = db.Column(db.String(32), nullable=False, default=ESTADO_BORRADOR, server_default=ESTADO_BORRADOR, index=True)
    observaciones = db.Column(db.String(8000), nullable=False, default="", server_default="")
    archivo_path = db.Column(db.String(512), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        db.UniqueConstraint("tipo", "codigo", name="uq_sgi_documentos_tipo_codigo"),
    )


class SgiDocumentoHistorial(db.Model):
    __tablename__ = "sgi_documentos_historial"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    documento_id = db.Column(
        db.Integer, db.ForeignKey("sgi_documentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    usuario = db.Column(db.String(256), nullable=False, default="", server_default="")
    accion = db.Column(db.String(64), nullable=False, index=True)
    detalle = db.Column(db.String(8000), nullable=False, default="", server_default="")

    documento = db.relationship("SgiDocumento", backref=db.backref("historial", lazy="dynamic", order_by="SgiDocumentoHistorial.fecha.desc()"))
