"""Notificaciones in-app (campana) del módulo SGI."""
from __future__ import annotations

from typing import Any

from flask import url_for
from sqlalchemy import select

from app.extensions import db
from app.models.sgi import (
    ESTADO_APROBADO,
    ESTADO_VIGENTE,
    SgiDocumento,
    SgiNotificacion,
    SgiProcedimientoRevision,
    TIPO_SLUGS,
)
from app.models.user import User
from app.services.sgi_documento_perfil_service import (
    perfiles_aplica_documento,
    users_with_perfiles,
)


SESSION_KEY_SGI_NOTIF_LAST_SEEN_ID = "sgi_notif_last_seen_id"


def users_to_notify_document_approved(doc: SgiDocumento, rev: SgiProcedimientoRevision) -> list[User]:
    """Usuarios activos con perfiles seleccionados para este procedimiento."""
    del rev  # reservado por si en el futuro la difusión depende de la revisión
    perfiles = perfiles_aplica_documento(doc.id)
    return users_with_perfiles(perfiles)


def create_approval_notifications(
    doc: SgiDocumento,
    rev: SgiProcedimientoRevision,
    *,
    actor_label: str,
) -> int:
    slug = TIPO_SLUGS.get(doc.tipo or "", "pg")
    enlace = url_for("sgi.procedimiento_vista", slug=slug, doc_id=doc.id, rev_id=rev.id)
    perfiles = perfiles_aplica_documento(doc.id)
    mensaje = f"Nuevo procedimiento aprobado: {doc.codigo} — {doc.titulo[:120]}"
    if actor_label:
        mensaje = f"{mensaje} ({rev.revision_label})"
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
    if count == 0 and perfiles:
        from flask import current_app

        current_app.logger.warning(
            "SGI aprobación %s: perfiles %s sin usuarios activos para notificar",
            doc.codigo,
            ",".join(perfiles),
        )
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
    items = list_notifications_for_user(int(user.id), limit=limit)
    if not items:
        return None
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
    if user is None:
        return False
    return sgi_notifications_nav({}, user, limit=1) is not None
