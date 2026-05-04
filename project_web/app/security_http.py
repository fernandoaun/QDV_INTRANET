"""Helpers HTTP: redirecciones seguras y endurecimiento de texto de entrada."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse


def safe_internal_redirect_target(next_raw: str | None) -> str | None:
    """
    Acepta solo rutas relativas del mismo sitio (/ruta…). Rechaza esquema, host, '//' y '\\\\'.
    """
    s = (next_raw or "").strip()
    if not s:
        return None
    if len(s) > 2048:
        return None
    low = s.lower()
    if low.startswith("//") or "\\\\" in s:
        return None
    parsed = urlparse(s)
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path if parsed.path else s
    if not path.startswith("/"):
        return None
    if path.startswith("//"):
        return None
    return path


def truncate_plain_text(raw: Any, *, max_len: int = 4096) -> str:
    t = "" if raw is None else str(raw).replace("\x00", " ").strip()
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def json_preview(data: dict[str, Any], *, max_len: int = 6000) -> str | None:
    try:
        s = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return None
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s
