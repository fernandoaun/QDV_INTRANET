from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User
from app.services import internal_chat_service as chat_svc
from app.user_roles import ROLE_OPERACIONES


def _login(client, username: str, password: str = "pytest-secret"):
    lg = client.get("/login")
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": m.group(1)},
        follow_redirects=False,
    )


def test_create_direct_thread_and_reply(app):
    with app.app_context():
        a = User(
            username="pytest_chat_a",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        b = User(
            username="pytest_chat_b",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add_all([a, b])
        db.session.commit()
        thread, err = chat_svc.create_thread(a, "Hola", target_user_ids=[int(b.id)])
        assert err is None
        assert thread is not None
        assert thread.kind == "direct"

        threads_b = chat_svc.list_threads_for_user(int(b.id))
        assert len(threads_b) == 1
        assert threads_b[0]["unread_count"] == 1

        msg, err2 = chat_svc.reply_to_thread(int(thread.id), b, "Hola de vuelta")
        assert err2 is None
        assert msg is not None

        messages = chat_svc.get_thread_messages(int(thread.id), int(a.id))
        assert messages is not None
        assert len(messages) == 2


def test_create_role_thread(app):
    with app.app_context():
        sender = User(
            username="pytest_chat_sender",
            password_hash=generate_password_hash("x"),
            is_admin=True,
            activo=True,
            rol="administrador",
        )
        ops = User(
            username="pytest_chat_ops",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add_all([sender, ops])
        db.session.commit()
        thread, err = chat_svc.create_thread(sender, "Aviso al perfil", target_role=ROLE_OPERACIONES)
        assert err is None
        assert thread is not None
        assert thread.kind == "role"
        assert chat_svc.user_can_access_thread(int(ops.id), int(thread.id)) is True


def test_chat_icon_renders_for_logged_user(app, client):
    with app.app_context():
        u = User(
            username="pytest_chat_ui",
            password_hash=generate_password_hash("pytest-secret"),
            is_admin=True,
            activo=True,
        )
        db.session.add(u)
        db.session.commit()

    _login(client, "pytest_chat_ui")
    r = client.get("/dashboard")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "appChatBtn" in html
    assert "bi-chat-dots" in html


def test_chat_api_create_and_list(app, client):
    with app.app_context():
        a = User(
            username="pytest_chat_api_a",
            password_hash=generate_password_hash("pytest-secret"),
            is_admin=True,
            activo=True,
        )
        b = User(
            username="pytest_chat_api_b",
            password_hash=generate_password_hash("pytest-secret"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add_all([a, b])
        db.session.commit()
        b_id = int(b.id)

    _login(client, "pytest_chat_api_a")
    lg = client.get("/dashboard")
    csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', lg.get_data(as_text=True))
    assert csrf is not None
    r = client.post(
        "/chat/api/threads",
        json={"body": "Mensaje de prueba", "target_user_ids": [b_id]},
        headers={"X-CSRFToken": csrf.group(1)},
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["thread"]["last_message_preview"] == "Mensaje de prueba"

    r2 = client.get("/chat/api/threads")
    assert r2.status_code == 200
    assert len(r2.get_json()["threads"]) >= 1
