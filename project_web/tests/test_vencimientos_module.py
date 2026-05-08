from __future__ import annotations

import re

import pytest

from werkzeug.security import generate_password_hash


@pytest.fixture
def angel_user(app):
    from app.extensions import db
    from app.models import User
    from app.user_roles import ROLE_SOLO_LECTURA_TOTAL

    with app.app_context():
        u = User(
            username="pytest_angel",
            password_hash=generate_password_hash("pytest-angel-pw"),
            is_admin=False,
            activo=True,
            rol=ROLE_SOLO_LECTURA_TOTAL,
        )
        db.session.add(u)
        db.session.commit()
        return u.username


@pytest.fixture
def angel_client(client, angel_user):
    lg = client.get("/login")
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = client.post(
        "/login",
        data={
            "username": angel_user,
            "password": "pytest-angel-pw",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    return client


def test_vencimientos_blocked_nonprivileged(mant_client):
    r = mant_client.get("/vencimientos/", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_vencimientos_admin_list_ok(auth_client):
    r = auth_client.get("/vencimientos/")
    assert r.status_code == 200


def test_vencimientos_angel_list_ok(angel_client):
    r = angel_client.get("/vencimientos/")
    assert r.status_code == 200


def test_vencimientos_angel_cannot_open_create(angel_client):
    r = angel_client.get("/vencimientos/nuevo", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_authenticated_mail_roundtrip(monkeypatch, app):
    """Smoke centralización SMTP sin servidor real."""
    import smtplib

    from app.services.mail_service import enviar_mail_texto_plano

    sent = {}

    class _DummySMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def login(self, *a, **k):
            return None

        def send_message(self, msg, *, mail_options=(), rcpt_options=()):
            sent["subject"] = msg["Subject"]

    monkeypatch.setattr(smtplib, "SMTP", _DummySMTP)

    with app.app_context():
        app.config["SMTP_HOST"] = "smtp.example.test"
        app.config["SMTP_PORT"] = 587
        app.config["MAIL_FROM"] = "noreply@example.test"
        enviar_mail_texto_plano(app, ["x@test.example"], "Hola", "cuerpo")
    assert "subject" in sent


def test_allowed_attachment_suffix_types():
    from app.services.vencimiento_service import allowed_attachment_suffix

    ok, err = allowed_attachment_suffix("certificado.PDF")
    assert ok is True and err is None
    ok, err = allowed_attachment_suffix("foto.JPEG")
    assert ok is True
    ok, err = allowed_attachment_suffix("evil.exe")
    assert ok is False and err
