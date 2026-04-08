from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from flask import current_app, jsonify, redirect, request, url_for

from app.auth_utils import current_user

F = TypeVar("F", bound=Callable[..., Any])


def require_api_docs_auth(f: F) -> F:
    """
    Si `API_DOCS_REQUIRE_AUTH` está activo: exige usuario (sesión o Bearer).
    openapi.json → 401 JSON; /docs → redirección al login.
    """

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any):
        if not current_app.config.get("API_DOCS_REQUIRE_AUTH"):
            return f(*args, **kwargs)
        if current_user() is not None:
            return f(*args, **kwargs)
        ep = request.endpoint or ""
        if ep == "api_v1.openapi_json":
            return jsonify(
                {
                    "error": "unauthorized",
                    "message": "Documentación API: iniciá sesión en la web o usá Authorization Bearer.",
                }
            ), 401
        return redirect(url_for("auth.login", next=request.path))

    return wrapped
