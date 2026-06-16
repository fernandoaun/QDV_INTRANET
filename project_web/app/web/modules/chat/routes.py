from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.auth_utils import current_user, login_required
from app.services import internal_chat_service as chat_svc

bp = Blueprint("chat", __name__, url_prefix="/chat")


def _require_user():
    u = current_user()
    if u is None:
        return None, (jsonify({"error": "no_auth"}), 403)
    return u, None


@bp.get("/api/threads")
@login_required
def api_threads():
    u, err = _require_user()
    if err:
        return err
    items = chat_svc.list_threads_for_user(int(u.id))
    return jsonify({"threads": items, "unread_total": chat_svc.unread_total_for_user(int(u.id))})


@bp.get("/api/threads/<int:thread_id>/messages")
@login_required
def api_thread_messages(thread_id: int):
    u, err = _require_user()
    if err:
        return err
    items = chat_svc.get_thread_messages(thread_id, int(u.id))
    if items is None:
        return jsonify({"error": "not_found"}), 404
    thread = next((t for t in chat_svc.list_threads_for_user(int(u.id), limit=200) if t["id"] == thread_id), None)
    return jsonify({"messages": items, "thread": thread})


@bp.post("/api/threads")
@login_required
def api_create_thread():
    u, err = _require_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    body = (data.get("body") or request.form.get("body") or "").strip()
    target_role = (data.get("target_role") or request.form.get("target_role") or "").strip() or None
    raw_ids = data.get("target_user_ids") or request.form.getlist("target_user_ids") or []
    user_ids: list[int] = []
    for raw in raw_ids:
        try:
            user_ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    thread, msg_err = chat_svc.create_thread(u, body, target_user_ids=user_ids, target_role=target_role)
    if thread is None:
        return jsonify({"error": "validation", "message": msg_err or "No se pudo crear la conversación."}), 400
    summary = chat_svc.thread_to_summary(thread, int(u.id))
    return jsonify({"thread": summary}), 201


@bp.post("/api/threads/<int:thread_id>/messages")
@login_required
def api_reply(thread_id: int):
    u, err = _require_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    body = (data.get("body") or request.form.get("body") or "").strip()
    msg, msg_err = chat_svc.reply_to_thread(thread_id, u, body)
    if msg is None:
        status = 404 if msg_err == "No tenés acceso a esta conversación." else 400
        return jsonify({"error": "validation", "message": msg_err or "No se pudo enviar."}), status
    item = chat_svc.message_to_dict(msg, viewer_id=int(u.id))
    return jsonify({"message": item}), 201


@bp.post("/api/threads/<int:thread_id>/read")
@login_required
def api_mark_read(thread_id: int):
    u, err = _require_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    raw = data.get("up_to_message_id") or request.form.get("up_to_message_id")
    up_to: int | None = None
    if raw is not None:
        try:
            up_to = int(raw)
        except (TypeError, ValueError):
            up_to = None
    ok = chat_svc.mark_thread_read(thread_id, int(u.id), up_to_message_id=up_to)
    if not ok:
        return jsonify({"error": "not_found"}), 404
    from app.extensions import db

    db.session.commit()
    return jsonify({"unread_total": chat_svc.unread_total_for_user(int(u.id))}), 200


@bp.get("/api/recipients")
@login_required
def api_recipients():
    u, err = _require_user()
    if err:
        return err
    return jsonify(
        {
            "users": chat_svc.list_active_users_for_picker(exclude_user_id=int(u.id)),
            "roles": chat_svc.role_options_for_picker(),
        }
    )
