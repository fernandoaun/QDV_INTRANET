"""Notificaciones in-app (campana) del módulo SGI."""
from __future__ import annotations

import re
from typing import Any

from flask import url_for
from sqlalchemy import select

from app.auth_utils import user_can_access_sgi, user_can_edit_sgi_documentos, user_display_name
from app.extensions import db
from app.models.sgi import (
    ESTADO_APROBADO,
    ESTADO_VIGENTE,
    SgiDocumento,
    SgiNotificacion,
    SgiProcedimientoRegistro,
    SgiProcedimientoRevision,
    TIPO_SLUGS,
)
from app.models.user import User
from app.user_roles import ROLE_LABELS, ROLE_OPERACIONES, normalize_stored_rol

SESSION_KEY_SGI_NOTIF_LAST_SEEN_ID = "sgi_notif_last_seen_id"

_REGISTRO_ROLE_ALIASES: dict[str, str] = {
    "operaciones": ROLE_OPERACIONES,
    "operativo": ROLE_OPERACIONES,
    "operador": ROLE_OPERACIONES,
    "logistica": "logistica",
    "logística": "logistica",
    "mantenimiento": "mantenimiento",
    "sgi": "sgi",
    "angel": "solo_lectura_total",
    "administrador": "administrador",
    "admin": "administrador",
}


def _roles_from_registros(rev: SgiProcedimientoRevision) -> set[str]:
    roles: set[str] = set()
    for reg in rev.registros.order_by(SgiProcedimientoRegistro.orden).all():
        texto = (reg.usuarios or "").lower()
        for token in re.split(r"[,;/\n]+", texto):
            key = token.strip()
            if not key:
                continue
            mapped = _REGISTRO_ROLE_ALIASES.get(key)
            if mapped:
                roles.add(mapped)
            elif key in ROLE_LABELS:
                roles.add(key)
    return roles


def _user_matches_registro_roles(user: User, roles: set[str]) -> bool:
    if not roles:
        return True
    if user.is_admin and "administrador" in roles:
        return True
    rol = normalize_stored_rol(user.rol)
    return rol in roles


def users_to_notify_document_approved(doc: SgiDocumento, rev: SgiProcedimientoRevision) -> list[User]:
    """Usuarios con acceso SGI a los que corresponde el documento (por registros o acceso general)."""
    roles = _roles_from_registros(rev)
    rows = db.session.scalars(select(User).where(User.activo.is_(True)).order_by(User.id)).all()
    out: list[User] = []
    seen: set[int] = set()
    for u in rows:
        if int(u.id) in seen:
            continue
        if not user_can_access_sgi(u):
            continue
        puede_editar = user_can_edit_sgi_documentos(u)
        if doc.estado not in (ESTADO_APROBADO, ESTADO_VIGENTE) and not puede_editar:
            continue
        if roles and not _user_matches_registro_roles(u, roles):
            continue
        seen.add(int(u.id))
        out.append(u)
    return out


def create_approval_notifications(
    doc: SgiDocumento,
    rev: SgiProcedimientoRevision,
    *,
    actor_label: str,
) -> int:
    slug = TIPO_SLUGS.get(doc.tipo or "", "pg")
    enlace = url_for("sgi.procedimiento_vista", slug=slug, doc_id=doc.id, rev_id=rev.id)
    mensaje = f"Documento aprobado: {doc.codigo} — {rev.revision_label}"
    if actor_label:
        mensaje = f"{mensaje} (por {actor_label})"
    users = users_to_notify_document_approved(doc, rev)
    count = 0
    for u in users:
        db.session.add(
            SgiNotificacion(
                user_id=int(u.id),
                documento_id=int(doc.id),
                revision_id=int(rev.id),
                mensaje=mensaje[:512],
                enlace=enlace[:512],
            )
        )
        count += 1
    return count


def list_notifications_for_user(user_id: int, *, limit: int = 25) -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(SgiNotificacion)
        .where(SgiNotificacion.user_id == int(user_id))
        .order_by(SgiNotificacion.id.desc())
        .limit(limit)
    ).all()
    items: list[dict[str, Any]] = []
    for n in rows:
        doc = n.documento
        items.append(
            {
                "id": int(n.id),
                "mensaje": n.mensaje,
                "enlace": n.enlace,
                "created_at": n.created_at.isoformat() if n.created_at else "",
                "codigo": doc.codigo if doc else "",
                "titulo": (doc.titulo[:80] + "…") if doc and len(doc.titulo) > 80 else (doc.titulo if doc else ""),
            }
        )
    return items


def sgi_notifications_nav(session: Any, user: User, *, limit: int = 25) -> dict[str, Any] | None:
    if not user_can_access_sgi(user):
        return None
    items = list_notifications_for_user(int(user.id), limit=limit)
    try:
        last_seen = int(session.get(SESSION_KEY_SGI_NOTIF_LAST_SEEN_ID) or 0)
    except (TypeError, ValueError):
        last_seen = 0
    unread_count = sum(1 for it in items if int(it["id"]) > last_seen)
    max_id = max((int(it["id"]) for it in items), default=last_seen)
    return {
        "entries": items,
        "unread_count": unread_count,
        "last_seen_id": last_seen,
        "max_id": max_id,
    }


def mark_sgi_notifications_seen(session: Any, up_to_id: int | None = None) -> None:
    if up_to_id is not None:
        session[SESSION_KEY_SGI_NOTIF_LAST_SEEN_ID] = int(up_to_id)
    else:
        session[SESSION_KEY_SGI_NOTIF_LAST_SEEN_ID] = 0


def user_can_view_sgi_notifications(user: User | None) -> bool:
    return user_can_access_sgi(user)
