from __future__ import annotations

import re

import pytest


@pytest.fixture
def planif_user(app):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User

    with app.app_context():
        u = User(
            username="pytest_planif",
            password_hash=generate_password_hash("pytest-planif-pw"),
            is_admin=False,
            activo=True,
            rol="operaciones",
        )
        db.session.add(u)
        db.session.commit()
        return u.username


@pytest.fixture
def planif_client(client, planif_user):
    lg = client.get("/login")
    assert lg.status_code == 200
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = client.post(
        "/login",
        data={
            "username": planif_user,
            "password": "pytest-planif-pw",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    return client


def test_planificacion_hub_requires_login(client):
    r = client.get("/planificacion/", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_planificacion_hub_ok(planif_client):
    r = planif_client.get("/planificacion/", follow_redirects=True)
    assert r.status_code == 200
    assert b"Planificaci" in r.data or b"planificaci" in r.data.lower()


def test_planificacion_create_and_list(planif_client, app):
    from datetime import date, timedelta

    lg = planif_client.get("/planificacion/nueva")
    assert lg.status_code == 200
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    t0 = date.today()
    t1 = t0 + timedelta(days=3)
    r = planif_client.post(
        "/planificacion/nueva",
        data={
            "csrf_token": m.group(1),
            "titulo": "Actividad pytest",
            "fecha_inicio": t0.isoformat(),
            "fecha_fin": t1.isoformat(),
            "estado": "pendiente",
            "prioridad": "alta",
            "categoria": "mantenimiento",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    tab = planif_client.get("/planificacion/tabla", follow_redirects=True)
    assert tab.status_code == 200
    assert b"Actividad pytest" in tab.data

    with app.app_context():
        from sqlalchemy import select

        from app.extensions import db
        from app.models import PlanificacionActividad

        row = db.session.scalar(select(PlanificacionActividad).order_by(PlanificacionActividad.id.desc()).limit(1))
        assert row is not None
        assert row.titulo == "Actividad pytest"
        assert row.duracion_dias >= 1


def test_planificacion_gantt_page(planif_client):
    r = planif_client.get("/planificacion/gantt", follow_redirects=True)
    assert r.status_code == 200
    assert b"frappe-gantt" in r.data.lower() or b"gantt" in r.data.lower()


def test_planificacion_api_json(planif_client):
    r = planif_client.get("/planificacion/api/tareas")
    assert r.status_code == 200
    assert r.is_json
    assert "tasks" in r.get_json()


def test_planificacion_export_csv(planif_client):
    r = planif_client.get("/planificacion/export.csv")
    assert r.status_code == 200
    assert b"titulo" in r.data.lower() or b"fecha_inicio" in r.data.lower()
