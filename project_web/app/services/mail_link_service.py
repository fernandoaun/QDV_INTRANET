"""URLs absolutas para enlaces en correos (fuera de un request HTTP activo)."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

from flask import url_for

log = logging.getLogger(__name__)


def resolve_public_base(app: Any) -> str:
    """Base pública https://… para armar enlaces en correos."""
    base = (app.config.get("APP_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if base:
        return base

    render_url = (os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if render_url:
        return render_url

    host = (os.environ.get("RENDER_EXTERNAL_HOSTNAME") or "").strip().rstrip("/")
    if host:
        return f"https://{host}"

    return ""


def is_absolute_public_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def public_abs_url(app: Any, endpoint: str, **values: Any) -> str:
    """Genera una URL absoluta usando APP_PUBLIC_BASE_URL (o fallback de Render)."""
    base = resolve_public_base(app)
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


def require_absolute_mail_url(app: Any, url: str, *, context: str) -> tuple[bool, str]:
    """Bloquea envíos con enlaces relativos (p. ej. /personal/… que el celular abre como «personal»)."""
    if is_absolute_public_url(url):
        return True, url
    base = resolve_public_base(app)
    detail = (
        f"Enlace inválido para {context}: falta URL pública del sitio. "
        "Definí APP_PUBLIC_BASE_URL=https://tu-sitio.com en el servidor (Environment en Render)."
    )
    if base:
        detail = (
            f"Enlace inválido para {context} ({url!r}). "
            "Revisá APP_PUBLIC_BASE_URL en el servidor."
        )
    log.error("%s URL generada: %r base=%r", context, url, base or None)
    return False, detail
