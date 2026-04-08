from __future__ import annotations

from app.extensions import db


class AppUploadedDocument(db.Model):
    """Documentos asociados a un módulo/campo (clave única por tipo)."""

    __tablename__ = "app_uploaded_documents"

    doc_key = db.Column(db.String(64), primary_key=True)
    stored_filename = db.Column(db.String(256), nullable=False)
    original_filename = db.Column(db.String(256), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)
