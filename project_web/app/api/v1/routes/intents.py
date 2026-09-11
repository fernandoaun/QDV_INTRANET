from __future__ import annotations

from flask import jsonify, request

from app.api.v1.blueprint import bp
from app.auth_utils import current_user
from app.extensions import limiter
from app.services import whatsapp_write_service as write_svc

LIMIT_WRITE = "20 per minute"


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.post("/intents/preview")
@limiter.limit(LIMIT_WRITE)
def api_intent_preview():
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    body = _json_body()
    module = str(body.get("module") or "").strip()
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    source = str(body.get("source") or "texto").strip() or "texto"
    try:
        out = write_svc.preview_and_token(u, module, payload, source)
    except PermissionError as exc:
        return jsonify({"error": "forbidden", "message": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    return jsonify(out)


@bp.post("/intents/confirm")
@limiter.limit(LIMIT_WRITE)
def api_intent_confirm():
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    body = _json_body()
    token = str(body.get("confirm_token") or "").strip()
    if not token:
        return jsonify({"error": "bad_request", "message": "Falta confirm_token."}), 400
    try:
        out = write_svc.confirm_and_save(u, token)
    except PermissionError as exc:
        return jsonify({"error": "forbidden", "message": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    return jsonify(out)
