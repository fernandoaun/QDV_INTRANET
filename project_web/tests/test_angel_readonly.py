from __future__ import annotations

import re

import pytest

from app.user_roles import ROLE_SOLO_LECTURA_TOTAL


@pytest.fixture
def angel_user(app):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User

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
    assert lg.status_code == 200
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


def test_angel_login_reaches_dashboard(angel_client):
    r = angel_client.get("/dashboard", follow_redirects=True)
    assert r.status_code == 200
    assert b"Panel" in r.data or b"panel" in r.data.lower()


def test_angel_get_salmuera_ok(angel_client):
    r = angel_client.get("/produccion/salmuera", follow_redirects=True)
    assert r.status_code == 200


def test_angel_post_salmuera_forbidden(angel_client):
    lg = angel_client.get("/produccion/salmuera")
    assert lg.status_code == 200
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = angel_client.post(
        "/produccion/salmuera",
        data={"csrf_token": m.group(1)},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)


def test_angel_admin_usuarios_list_ok(angel_client):
    r = angel_client.get("/admin/usuarios", follow_redirects=True)
    assert r.status_code == 200


def test_angel_cannot_create_user(angel_client):
    lg = angel_client.get("/admin/usuarios")
    assert lg.status_code == 200
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = angel_client.post(
        "/admin/usuarios/nuevo",
        data={
            "csrf_token": m.group(1),
            "username": "no_debe_existir",
            "password": "secret12",
            "password2": "secret12",
            "rol": "operaciones",
            "activo": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)


def test_angel_api_entregas_ok(angel_client):
    r = angel_client.get("/api/v1/entregas")
    assert r.status_code == 200
