"""Escritura de eventos en `security_audit_logs`. Fallos aquí no deben impedir la operación principal."""

from __future__ import annotations

from typing import Any

from flask import has_request_context, request

from app.extensions import db
from app.models.security_audit import SecurityAuditLog
from app.models.user import User


def _client_ip() -> str | None:
    if not has_request_context():
        return None
    # Sin confiar en X-Forwarded-For salvo detrás de proxy conocido configurado por el host.
    return (request.remote_addr or "").strip() or None


def _client_ua() -> str | None:
    if not has_request_context():
        return None
    ua = (request.headers.get("User-Agent") or "").strip()
    if not ua:
        return None
    return ua[:512]


def record_event(
    *,
    action: str,
    module: str = "general",
    actor: User | None = None,
    actor_username: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    detail: str | None = None,
    ip_override: str | None = None,
    user_agent_override: str | None = None,
) -> None:
    """Persiste un evento de auditoría. Ignora errores de BD."""
    uid = None
    uname = (actor_username or "").strip() or None
    if actor is not None:
        uid = int(actor.id)
        uname = uname or (actor.username or "").strip() or None

    row = SecurityAuditLog(
        actor_user_id=uid,
        actor_username=uname,
        action=str(action)[:64],
        module=str(module)[:64],
        entity_type=(entity_type[:64] if entity_type else None),
        entity_id=entity_id,
        ip=(ip_override or _client_ip()),
        user_agent=user_agent_override or _client_ua(),
        old_value=old_value,
        new_value=new_value,
        detail=detail,
    )
    try:
        db.session.add(row)
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            from flask import current_app

            current_app.logger.exception("security_audit_service: no se pudo guardar audit action=%s", action)
        except Exception:
            pass


def coerce_text(value: Any, *, max_len: int = 8000) -> str | None:
    """Texto único campo para payloads JSON o resúmenes; trunca."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s
