from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WhatsappAviso(db.Model):
    """Copia por WhatsApp de un aviso que salió por mail; la envía el gateway (OpenClaw) al consultarla."""

    __tablename__ = "whatsapp_avisos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    telefono_e164 = db.Column(db.String(20), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    creado_en = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    enviado_en = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    intentos = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    ultimo_error = db.Column(db.String(500), nullable=False, default="", server_default="")
    # Archivo a mandar junto con el texto (ruta relativa a la raíz de uploads) y nombre visible.
    adjunto_path = db.Column(db.String(255), nullable=False, default="", server_default="")
    adjunto_nombre = db.Column(db.String(160), nullable=False, default="", server_default="")
