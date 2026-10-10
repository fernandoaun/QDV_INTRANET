from __future__ import annotations

from flask import g, jsonify, request

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_SHIFT_STATUS
from app.extensions import limiter
from app.services import whatsapp_avisos_service
from app.services.whatsapp_identity import whatsapp_numeros_habilitados


@bp.get("/whatsapp/allowlist")
@limiter.limit(LIMIT_SHIFT_STATUS)
def api_whatsapp_allowlist():
    """Números que el gateway de WhatsApp deja pasar (solo con el token de servicio)."""
    if not getattr(g, "_qdv_api_service", False):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"numeros": whatsapp_numeros_habilitados()})


@bp.get("/whatsapp/avisos")
@limiter.limit(LIMIT_SHIFT_STATUS)
def api_whatsapp_avisos_pendientes():
    """Avisos (copia de mails) que el gateway tiene que mandar por WhatsApp (solo token de servicio)."""
    if not getattr(g, "_qdv_api_service", False):
        return jsonify({"error": "unauthorized"}), 401
    try:
        limit = int(request.args.get("limit") or 20)
    except ValueError:
        limit = 20
    return jsonify({"avisos": whatsapp_avisos_service.pendientes(limit)})


@bp.post("/whatsapp/avisos/<int:aviso_id>/resultado")
@limiter.limit(LIMIT_SHIFT_STATUS)
def api_whatsapp_aviso_resultado(aviso_id: int):
    """El gateway informa si pudo mandar el aviso: {"ok": true} o {"ok": false, "error": "..."}."""
    if not getattr(g, "_qdv_api_service", False):
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    ok = bool(data.get("ok"))
    actualizado = whatsapp_avisos_service.registrar_resultado(aviso_id, ok, str(data.get("error") or ""))
    return jsonify({"ok": True, "actualizado": actualizado})
