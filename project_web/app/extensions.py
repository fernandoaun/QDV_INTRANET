from __future__ import annotations

import hashlib

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect


def _api_rate_limit_key() -> str:
    """API: bucket por token Bearer (hash) si hay cabecera; si no, por IP."""
    from flask import request

    path = request.path or ""
    if path.startswith("/api/v1"):
        auth = (request.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer ") and len(auth) > 7:
            digest = hashlib.sha256(auth.encode("utf-8")).hexdigest()[:24]
            return f"api_bearer:{digest}"
    return get_remote_address()


limiter = Limiter(key_func=_api_rate_limit_key)


@limiter.request_filter
def _rate_limit_exempt_non_api_v1() -> bool:
    """True = no aplicar límite (todo fuera de /api/v1 o con rate limit desactivado)."""
    from flask import current_app, request

    if not current_app.config.get("RATELIMIT_ENABLED", True):
        return True
    p = request.path or ""
    if p in ("/api/v1/openapi.json", "/api/v1/docs"):
        return True
    return not p.startswith("/api/v1")


db = SQLAlchemy()
csrf = CSRFProtect()
