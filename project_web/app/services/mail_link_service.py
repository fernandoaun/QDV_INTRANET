"""URLs absolutas para enlaces en correos (fuera de un request HTTP activo)."""

from __future__ import annotations

import logging
from typing import Any

from flask import url_for

log = logging.getLogger(__name__)


def public_abs_url(app: Any, endpoint: str, **values: Any) -> str:
    """Genera una URL absoluta usando APP_PUBLIC_BASE_URL (o fallback de Render)."""
    base = (app.config.get("APP_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    with app.app_context():
        with app.test_request_context():
            path = url_for(endpoint, _external=False, **values)
        if not path.startswith("/"):
            path = "/" + path
        if base:
            return f"{base}{path}"
        try:
            with app.test_request_context():
                return url_for(endpoint, _external=True, **values)
        except RuntimeError:
            log.warning(
                "Enlace de correo sin URL pública absoluta (%s). Definí APP_PUBLIC_BASE_URL.",
                endpoint,
            )
            return path


def login_url_for_path(app: Any, dest_path: str) -> str:
    """Enlace al login que redirige a una ruta interna tras autenticarse."""
    dest = (dest_path or "").strip()
    if not dest.startswith("/"):
        dest = "/" + dest
    return public_abs_url(app, "auth.login", next=dest)
