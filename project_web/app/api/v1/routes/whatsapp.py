from __future__ import annotations

from flask import g, jsonify

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_SHIFT_STATUS
from app.extensions import limiter
from app.services.whatsapp_identity import whatsapp_numeros_habilitados


@bp.get("/whatsapp/allowlist")
@limiter.limit(LIMIT_SHIFT_STATUS)
def api_whatsapp_allowlist():
    """Números que el gateway de WhatsApp deja pasar (solo con el token de servicio)."""
    if not getattr(g, "_qdv_api_service", False):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"numeros": whatsapp_numeros_habilitados()})
