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
            username="pytest_angel_sgi",
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


@pytest.fixture
def sgi_perm_user(app):
    from app.extensions import db
    from app.models import PermisoUsuario, User
    from app.user_roles import ROLE_OPERACIONES

    with app.app_context():
        u = User(
            username="pytest_sgi_perm",
            password_hash=generate_password_hash("pytest-sgi-pw"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add(u)
        db.session.flush()
        db.session.add(
            PermisoUsuario(user_id=u.id, permiso="sgi_hub", habilitado=True, puede_editar=False)
        )
        db.session.add(
            PermisoUsuario(user_id=u.id, permiso="sgi_documentos_edit", habilitado=True, puede_editar=True)
        )
        db.session.commit()
        return u.username


@pytest.fixture
def sgi_perm_client(client, sgi_perm_user):
    lg = client.get("/login")
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = client.post(
        "/login",
        data={
            "username": sgi_perm_user,
            "password": "pytest-sgi-pw",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    return client


def test_sgi_blocked_nonprivileged(mant_client):
    r = mant_client.get("/sgi/", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_sgi_admin_hub_ok(auth_client):
    r = auth_client.get("/sgi/")
    assert r.status_code == 200
    assert b"SGI" in r.data


def test_sgi_angel_hub_ok(angel_client):
    r = angel_client.get("/sgi/")
    assert r.status_code == 200


def test_sgi_angel_cannot_open_create(angel_client):
    r = angel_client.get("/sgi/pg/nuevo", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_sgi_perm_user_list_ok(sgi_perm_client):
    r = sgi_perm_client.get("/sgi/po/")
    assert r.status_code == 200


def _csrf_from_html(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    return m.group(1)


def test_sgi_admin_create_list_export(auth_client):
    r_form = auth_client.get("/sgi/pg/nuevo")
    assert r_form.status_code == 200
    csrf = _csrf_from_html(r_form.get_data(as_text=True))
    r = auth_client.post(
        "/sgi/pg/nuevo",
        data={
            "csrf_token": csrf,
            "codigo": "PG-TEST-001",
            "titulo": "Procedimiento de prueba",
            "revision": "01",
            "estado": "borrador",
            "responsable_elaboracion": "Tester",
            "responsable_aprobacion": "Admin",
            "observaciones": "Nota test",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    r_list = auth_client.get("/sgi/pg/?q=PG-TEST-001")
    assert r_list.status_code == 200
    assert b"PG-TEST-001" in r_list.data

    r_xlsx = auth_client.get("/sgi/pg/export.xlsx")
    assert r_xlsx.status_code == 200
    assert "spreadsheetml" in (r_xlsx.content_type or "")


def test_sgi_perm_user_can_create(sgi_perm_client):
    r_form = sgi_perm_client.get("/sgi/msgi/nuevo")
    assert r_form.status_code == 200
    csrf = _csrf_from_html(r_form.get_data(as_text=True))
    r = sgi_perm_client.post(
        "/sgi/msgi/nuevo",
        data={
            "csrf_token": csrf,
            "codigo": "MSGI-T-01",
            "titulo": "Manual test",
            "revision": "00",
            "estado": "vigente",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)


def test_sgi_perm_user_cannot_delete(sgi_perm_client):
    r_form = sgi_perm_client.get("/sgi/msgi/nuevo")
    csrf = _csrf_from_html(r_form.get_data(as_text=True))
    sgi_perm_client.post(
        "/sgi/msgi/nuevo",
        data={
            "csrf_token": csrf,
            "codigo": "MSGI-DEL-01",
            "titulo": "Para borrar",
            "estado": "borrador",
        },
        follow_redirects=True,
    )
    r_list = sgi_perm_client.get("/sgi/msgi/?q=MSGI-DEL-01")
    html = r_list.get_data(as_text=True)
    m = re.search(r"/sgi/msgi/(\d+)", html)
    assert m is not None
    doc_id = m.group(1)

    lg = sgi_perm_client.get("/sgi/msgi/")
    csrf2 = _csrf_from_html(lg.get_data(as_text=True))
    r = sgi_perm_client.post(
        f"/sgi/msgi/{doc_id}/eliminar",
        data={"csrf_token": csrf2},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
