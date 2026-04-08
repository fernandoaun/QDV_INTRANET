from __future__ import annotations

import os
import re

import pytest

os.environ["FLASK_ENV"] = "testing"


@pytest.fixture
def app():
    from app import create_app
    from app.extensions import db

    application = create_app()
    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_user(app):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User

    with app.app_context():
        u = User(
            username="pytest_admin",
            password_hash=generate_password_hash("pytest-secret"),
            is_admin=True,
            activo=True,
        )
        db.session.add(u)
        db.session.commit()
        return u.username


@pytest.fixture
def mant_user(app):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User
    from app.user_roles import ROLE_MANTENIMIENTO

    with app.app_context():
        u = User(
            username="pytest_mant",
            password_hash=generate_password_hash("pytest-mant-pw"),
            is_admin=False,
            activo=True,
            rol=ROLE_MANTENIMIENTO,
        )
        db.session.add(u)
        db.session.commit()
        return u.username


@pytest.fixture
def mant_client(client, mant_user):
    lg = client.get("/login")
    assert lg.status_code == 200
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = client.post(
        "/login",
        data={
            "username": mant_user,
            "password": "pytest-mant-pw",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    return client


@pytest.fixture
def auth_client(client, admin_user):
    lg = client.get("/login")
    assert lg.status_code == 200
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = client.post(
        "/login",
        data={
            "username": admin_user,
            "password": "pytest-secret",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), (r.status_code, html[:200] if r.status_code != 302 else "")
    return client
