"""Servicio de chat interno entre usuarios y perfiles."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.auth_utils import user_display_name
from app.extensions import db
from app.models.internal_chat import (
    KIND_DIRECT,
    KIND_GROUP,
    KIND_ROLE,
    InternalChatMessage,
    InternalChatParticipant,
    InternalChatThread,
)
from app.models.user import User
from app.user_roles import ROLE_LABELS, normalize_stored_rol, validate_rol_submitted


def list_active_users_for_picker(*, exclude_user_id: int | None = None) -> list[dict[str, Any]]:
    q = select(User).where(User.activo.is_(True)).order_by(User.username.asc())
    if exclude_user_id is not None:
        q = q.where(User.id != int(exclude_user_id))
    rows = db.session.scalars(q).all()
    return [
        {
            "id": int(u.id),
            "username": u.username,
            "label": user_display_name(u) or u.username,
            "rol": normalize_stored_rol(u.rol),
            "rol_label": ROLE_LABELS.get(normalize_stored_rol(u.rol), normalize_stored_rol(u.rol)),
        }
        for u in rows
    ]


def role_options_for_picker() -> list[dict[str, str]]:
    return [{"value": k, "label": v} for k, v in ROLE_LABELS.items()]


def _participant_for(user_id: int, thread_id: int) -> InternalChatParticipant | None:
    return db.session.scalar(
        select(InternalChatParticipant).where(
            InternalChatParticipant.thread_id == int(thread_id),
            InternalChatParticipant.user_id == int(user_id),
        )
    )


def user_can_access_thread(user_id: int, thread_id: int) -> bool:
    return _participant_for(user_id, thread_id) is not None


def _users_by_ids(user_ids: list[int]) -> list[User]:
    if not user_ids:
        return []
    rows = db.session.scalars(select(User).where(User.id.in_(user_ids), User.activo.is_(True))).all()
    by_id = {int(u.id): u for u in rows}
    return [by_id[i] for i in user_ids if i in by_id]


def _users_for_role(role: str) -> list[User]:
    norm = validate_rol_submitted(role) or normalize_stored_rol(role)
    rows = db.session.scalars(select(User).where(User.activo.is_(True))).all()
    return [u for u in rows if normalize_stored_rol(u.rol) == norm or (norm == "administrador" and u.is_admin)]


def _thread_title_for_users(sender: User, recipients: list[User], *, kind: str, role: str | None = None) -> str:
    if kind == KIND_ROLE and role:
        label = ROLE_LABELS.get(role, role)
        return f"Perfil: {label}"
    names = [user_display_name(u) or u.username for u in recipients if int(u.id) != int(sender.id)]
    if not names:
        names = [user_display_name(u) or u.username for u in recipients]
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return ", ".join(names)
    return f"{names[0]}, {names[1]} y {len(names) - 2} más"


def _find_direct_thread(user_a: int, user_b: int) -> InternalChatThread | None:
    ids = sorted([int(user_a), int(user_b)])
    subq = (
        select(InternalChatParticipant.thread_id)
        .where(InternalChatParticipant.user_id.in_(ids))
        .group_by(InternalChatParticipant.thread_id)
        .having(func.count(InternalChatParticipant.id) == 2)
    )
    thread_ids = db.session.scalars(subq).all()
    for tid in thread_ids:
        thread = db.session.get(InternalChatThread, int(tid))
        if thread is None or thread.kind != KIND_DIRECT:
            continue
        part_ids = {
            int(p.user_id)
            for p in db.session.scalars(
                select(InternalChatParticipant).where(InternalChatParticipant.thread_id == int(tid))
            ).all()
        }
        if part_ids == set(ids):
            return thread
    return None


def _add_participants(thread: InternalChatThread, user_ids: set[int]) -> None:
    existing = {
        int(p.user_id)
        for p in db.session.scalars(
            select(InternalChatParticipant).where(InternalChatParticipant.thread_id == int(thread.id))
        ).all()
    }
    for uid in user_ids:
        if uid in existing:
            continue
        db.session.add(InternalChatParticipant(thread_id=int(thread.id), user_id=int(uid)))


def message_to_dict(msg: InternalChatMessage, *, viewer_id: int | None = None) -> dict[str, Any]:
    sender = msg.sender
    item = {
        "id": int(msg.id),
        "thread_id": int(msg.thread_id),
        "body": msg.body,
        "created_at": msg.created_at.isoformat() if msg.created_at else "",
        "sender_id": int(msg.sender_id) if msg.sender_id else None,
        "sender_label": user_display_name(sender) if sender else "Usuario",
        "is_mine": False,
    }
    if viewer_id is not None and item["sender_id"] == int(viewer_id):
        item["is_mine"] = True
    return item


def thread_to_summary(thread: InternalChatThread, viewer_id: int) -> dict[str, Any]:
    part = _participant_for(viewer_id, int(thread.id))
    last_msg = db.session.scalar(
        select(InternalChatMessage)
        .where(InternalChatMessage.thread_id == int(thread.id))
        .order_by(InternalChatMessage.id.desc())
        .limit(1)
    )
    last_read = int(part.last_read_message_id) if part else 0
    unread = 0
    if last_msg is not None:
        unread = max(0, int(last_msg.id) - last_read)
    preview = ""
    preview_at = ""
    if last_msg is not None:
        preview = (last_msg.body or "")[:120]
        preview_at = last_msg.created_at.isoformat() if last_msg.created_at else ""
    return {
        "id": int(thread.id),
        "kind": thread.kind,
        "title": thread.title or "Conversación",
        "target_role": thread.target_role,
        "last_message_preview": preview,
        "last_message_at": preview_at,
        "unread_count": unread,
    }


def list_threads_for_user(user_id: int, *, limit: int = 30) -> list[dict[str, Any]]:
    thread_ids = db.session.scalars(
        select(InternalChatParticipant.thread_id)
        .where(InternalChatParticipant.user_id == int(user_id))
        .order_by(InternalChatParticipant.id.desc())
    ).all()
    if not thread_ids:
        return []
    threads = db.session.scalars(
        select(InternalChatThread).where(InternalChatThread.id.in_(thread_ids))
    ).all()
    by_id = {int(t.id): t for t in threads}
    items = [thread_to_summary(by_id[tid], user_id) for tid in thread_ids if tid in by_id]
    items.sort(key=lambda x: x["last_message_at"] or "", reverse=True)
    return items[:limit]


def unread_total_for_user(user_id: int) -> int:
    return sum(t["unread_count"] for t in list_threads_for_user(user_id, limit=100))


def get_thread_messages(thread_id: int, viewer_id: int, *, limit: int = 100) -> list[dict[str, Any]] | None:
    if not user_can_access_thread(viewer_id, thread_id):
        return None
    rows = db.session.scalars(
        select(InternalChatMessage)
        .where(InternalChatMessage.thread_id == int(thread_id))
        .order_by(InternalChatMessage.id.desc())
        .limit(limit)
    ).all()
    items = [message_to_dict(m, viewer_id=viewer_id) for m in reversed(rows)]
    return items


def mark_thread_read(thread_id: int, user_id: int, *, up_to_message_id: int | None = None) -> bool:
    part = _participant_for(user_id, thread_id)
    if part is None:
        return False
    if up_to_message_id is None:
        last_id = db.session.scalar(
            select(func.max(InternalChatMessage.id)).where(InternalChatMessage.thread_id == int(thread_id))
        )
        up_to_message_id = int(last_id or 0)
    part.last_read_message_id = max(int(part.last_read_message_id), int(up_to_message_id))
    return True


def create_thread(
    sender: User,
    body: str,
    *,
    target_user_ids: list[int] | None = None,
    target_role: str | None = None,
) -> tuple[InternalChatThread | None, str | None]:
    text = (body or "").strip()
    if not text:
        return None, "Escribí un mensaje."
    if len(text) > 4000:
        return None, "El mensaje es demasiado largo (máx. 4000 caracteres)."

    sender_id = int(sender.id)
    user_ids = sorted({int(i) for i in (target_user_ids or []) if int(i) != sender_id})
    role = validate_rol_submitted(target_role) if target_role else None

    if role:
        recipients = _users_for_role(role)
        if not recipients:
            return None, "No hay usuarios activos con ese perfil."
        participant_ids = {sender_id, *(int(u.id) for u in recipients)}
        thread = InternalChatThread(
            kind=KIND_ROLE,
            title=_thread_title_for_users(sender, recipients, kind=KIND_ROLE, role=role),
            target_role=role,
            created_by_id=sender_id,
        )
        db.session.add(thread)
        db.session.flush()
        _add_participants(thread, participant_ids)
    elif len(user_ids) == 1:
        other_id = user_ids[0]
        other_users = _users_by_ids([other_id])
        if not other_users:
            return None, "Destinatario no encontrado o inactivo."
        existing = _find_direct_thread(sender_id, other_id)
        if existing is not None:
            thread = existing
        else:
            thread = InternalChatThread(
                kind=KIND_DIRECT,
                title=_thread_title_for_users(sender, other_users, kind=KIND_DIRECT),
                created_by_id=sender_id,
            )
            db.session.add(thread)
            db.session.flush()
            _add_participants(thread, {sender_id, other_id})
    elif len(user_ids) > 1:
        recipients = _users_by_ids(user_ids)
        if len(recipients) != len(user_ids):
            return None, "Alguno de los destinatarios no existe o está inactivo."
        participant_ids = {sender_id, *(int(u.id) for u in recipients)}
        thread = InternalChatThread(
            kind=KIND_GROUP,
            title=_thread_title_for_users(sender, recipients, kind=KIND_GROUP),
            created_by_id=sender_id,
        )
        db.session.add(thread)
        db.session.flush()
        _add_participants(thread, participant_ids)
    else:
        return None, "Elegí al menos un destinatario o un perfil."

    msg = InternalChatMessage(thread_id=int(thread.id), sender_id=sender_id, body=text)
    db.session.add(msg)
    db.session.flush()
    mark_thread_read(int(thread.id), sender_id, up_to_message_id=int(msg.id))
    db.session.commit()
    return thread, None


def reply_to_thread(thread_id: int, sender: User, body: str) -> tuple[InternalChatMessage | None, str | None]:
    text = (body or "").strip()
    if not text:
        return None, "Escribí un mensaje."
    if len(text) > 4000:
        return None, "El mensaje es demasiado largo (máx. 4000 caracteres)."
    if not user_can_access_thread(int(sender.id), thread_id):
        return None, "No tenés acceso a esta conversación."

    msg = InternalChatMessage(thread_id=int(thread_id), sender_id=int(sender.id), body=text)
    db.session.add(msg)
    db.session.flush()
    mark_thread_read(int(thread_id), int(sender.id), up_to_message_id=int(msg.id))
    db.session.commit()
    return msg, None


def chat_nav_summary(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    unread = unread_total_for_user(int(user.id))
    return {"unread_count": unread}
