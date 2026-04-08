from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Blueprint

_bearer_hook_installed = False


def register_api_bearer(bp: Blueprint) -> None:
    """Autenticación opcional Authorization: Bearer <token> en rutas /api/v1."""
    global _bearer_hook_installed
    if _bearer_hook_installed:
        return
    _bearer_hook_installed = True

    @bp.before_request
    def _api_bearer_auth():
        from flask import current_app, g, jsonify, request

        from app.auth_utils import perm_sets_for_user
        from app.extensions import db
        from app.models import User

        token_cfg = (current_app.config.get("API_BEARER_TOKEN") or "").strip()
        uid = current_app.config.get("API_BEARER_USER_ID")
        if not token_cfg or uid is None:
            return None

        auth = (request.headers.get("Authorization") or "").strip()
        parts = auth.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        raw = parts[1].strip()
        if not raw:
            return jsonify({"error": "unauthorized", "message": "Token vacío."}), 401

        if not secrets.compare_digest(raw, token_cfg):
            return jsonify({"error": "unauthorized", "message": "Token inválido."}), 401

        user = db.session.get(User, int(uid))
        if user is None or not user.activo:
            return jsonify({"error": "unauthorized", "message": "Usuario API inactivo o inexistente."}), 401

        p_view, p_edit = perm_sets_for_user(user)
        g._qdv_api_user = user
        g._qdv_api_perms_view = frozenset(p_view)
        g._qdv_api_perms_edit = frozenset(p_edit)
        return None
