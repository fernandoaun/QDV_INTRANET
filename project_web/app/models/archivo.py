from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db

KIND_PROCEDIMIENTO = "procedimiento"
KIND_REGISTRO = "registro"
KINDS = (KIND_PROCEDIMIENTO, KIND_REGISTRO)
KIND_LABELS = {
    KIND_PROCEDIMIENTO: "Procedimientos",
    KIND_REGISTRO: "Registros",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ArchivoSubmodulo(db.Model):
    """Carpeta configurable: un procedimiento o un tipo de registro externo."""

    __tablename__ = "archivo_submodulos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kind = db.Column(db.String(32), nullable=False, index=True)
    nombre = db.Column(db.String(256), nullable=False)
    codigo = db.Column(db.String(64), nullable=False, default="", server_default="")
    descripcion = db.Column(db.String(2000), nullable=False, default="", server_default="")
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    cargas = db.relationship("ArchivoCarga", back_populates="submodulo", lazy="dynamic")

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


class ArchivoCarga(db.Model):
    """Archivo subido (planilla, PDF, foto) hecho fuera del sistema."""

    __tablename__ = "archivo_cargas"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    submodulo_id = db.Column(
        db.Integer, db.ForeignKey("archivo_submodulos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sgi_documento_id = db.Column(
        db.Integer, db.ForeignKey("sgi_documentos.id", ondelete="CASCADE"), nullable=True, index=True
    )
    sgi_registro_id = db.Column(
        db.Integer, db.ForeignKey("sgi_procedimiento_registros.id", ondelete="SET NULL"), nullable=True, index=True
    )
    registro_clave = db.Column(db.String(256), nullable=False, default="", server_default="", index=True)
    titulo = db.Column(db.String(256), nullable=False, default="", server_default="")
    fecha_documento = db.Column(db.Date, nullable=True, index=True)
    notas = db.Column(db.String(2000), nullable=False, default="", server_default="")
    original_filename = db.Column(db.String(256), nullable=False)
    stored_path = db.Column(db.String(1024), nullable=False)
    mime_type = db.Column(db.String(128), nullable=False, default="", server_default="")
    size_bytes = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)

    submodulo = db.relationship("ArchivoSubmodulo", back_populates="cargas")
    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])
