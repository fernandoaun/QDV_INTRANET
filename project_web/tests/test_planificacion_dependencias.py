from __future__ import annotations

import re
from datetime import date, timedelta

import pytest


@pytest.fixture
def planif_user(app):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User

    with app.app_context():
        u = User(
            username="pytest_planif_dep",
            password_hash=generate_password_hash("pytest-planif-dep-pw"),
            is_admin=False,
            activo=True,
            rol="operaciones",
        )
        db.session.add(u)
        db.session.commit()
        return u.username


@pytest.fixture
def dep_client(client, planif_user):
    lg = client.get("/login")
    assert lg.status_code == 200
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = client.post(
        "/login",
        data={
            "username": planif_user,
            "password": "pytest-planif-dep-pw",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    return client


def _csrf(c):
    lg = c.get("/planificacion/nueva")
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    return m.group(1)


def _create_activity(c, title: str, t0: date, t1: date) -> int:
    token = _csrf(c)
    r = c.post(
        "/planificacion/nueva",
        data={
            "csrf_token": token,
            "titulo": title,
            "fecha_inicio": t0.isoformat(),
            "fecha_fin": t1.isoformat(),
            "estado": "pendiente",
            "prioridad": "media",
            "categoria": "otro",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    from sqlalchemy import select

    from app.extensions import db
    from app.models import PlanificacionActividad

    with c.application.app_context():
        row = db.session.scalar(select(PlanificacionActividad).where(PlanificacionActividad.titulo == title))
        assert row is not None
        return int(row.id)


def test_cycle_rejected(dep_client, app):
    t0 = date(2026, 5, 1)
    t1 = t0 + timedelta(days=2)
    id_a = _create_activity(dep_client, "dep_cycle_A", t0, t1)
    id_b = _create_activity(dep_client, "dep_cycle_B", t0, t1)
    token = _csrf(dep_client)
    r = dep_client.post(
        "/planificacion/editar/" + str(id_b),
        data={
            "csrf_token": token,
            "titulo": "dep_cycle_B",
            "fecha_inicio": t0.isoformat(),
            "fecha_fin": t1.isoformat(),
            "estado": "pendiente",
            "prioridad": "media",
            "categoria": "otro",
            "dep_pre_id": str(id_a),
            "dep_tipo": "FS",
            "dep_lag": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    token = _csrf(dep_client)
    r2 = dep_client.post(
        "/planificacion/editar/" + str(id_a),
        data={
            "csrf_token": token,
            "titulo": "dep_cycle_A",
            "fecha_inicio": t0.isoformat(),
            "fecha_fin": t1.isoformat(),
            "estado": "pendiente",
            "prioridad": "media",
            "categoria": "otro",
            "dep_pre_id": str(id_b),
            "dep_tipo": "FS",
            "dep_lag": "0",
        },
        follow_redirects=True,
    )
    assert r2.status_code == 200
    assert b"ciclo" in r2.data.lower() or b"circular" in r2.data.lower()


def test_fs_blocks_en_curso(dep_client, app):
    t0 = date(2026, 6, 1)
    t1 = t0 + timedelta(days=2)
    id_a = _create_activity(dep_client, "dep_fs_pred", t0, t1)
    id_b = _create_activity(dep_client, "dep_fs_suc", t0, t1)
    token = _csrf(dep_client)
    r = dep_client.post(
        "/planificacion/editar/" + str(id_b),
        data={
            "csrf_token": token,
            "titulo": "dep_fs_suc",
            "fecha_inicio": t0.isoformat(),
            "fecha_fin": t1.isoformat(),
            "estado": "pendiente",
            "prioridad": "media",
            "categoria": "otro",
            "dep_pre_id": str(id_a),
            "dep_tipo": "FS",
            "dep_lag": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    tab = dep_client.get("/planificacion/tabla", follow_redirects=True)
    assert tab.status_code == 200
    token = _csrf(dep_client)
    r2 = dep_client.post(
        "/planificacion/estado/" + str(id_b),
        data={"csrf_token": token, "estado": "en_curso"},
        follow_redirects=True,
    )
    assert r2.status_code == 200
    assert b"FS" in r2.data or b"predecesora" in r2.data.lower() or b"finalizada" in r2.data.lower()
