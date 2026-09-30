from __future__ import annotations

import re

import pytest
from werkzeug.security import generate_password_hash


@pytest.fixture
def lab(app, client):
    """Responsable de laboratorio logueada + un operador (sin turno abierto todavía)."""
    from app.extensions import db
    from app.models import User

    with app.app_context():
        lab_u = User(username="pytest_resp_lab", password_hash=generate_password_hash("pw-lab"), activo=True,
                     is_admin=False, rol="responsable_laboratorio", nombre_completo="Laura Lab")
        oper = User(username="pytest_oper_turno", password_hash=generate_password_hash("pw-op"), activo=True,
                    is_admin=False, rol="operaciones", nombre_completo="Oscar Operador")
        db.session.add_all([lab_u, oper])
        db.session.commit()
        ids = (lab_u.id, oper.id)
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    r = client.post("/login", data={"username": "pytest_resp_lab", "password": "pw-lab", "csrf_token": tok})
    assert r.status_code in (302, 303)
    return client, ids


def _abrir_turno(app, oper_id):
    from app.extensions import db
    from app.models import ShiftSession

    with app.app_context():
        db.session.add(ShiftSession(user_id=oper_id, effective_role="operaciones", started_at_iso="2026-09-30T06:00:00",
                                    status="open", created_at_iso="2026-09-30T06:00:00", updated_at_iso="2026-09-30T06:00:00"))
        db.session.commit()


def _ultimo_agua(app):
    from sqlalchemy import select

    from app.extensions import db
    from app.models import AguaRegistro

    with app.app_context():
        r = db.session.scalar(select(AguaRegistro).order_by(AguaRegistro.id.desc()).limit(1))
        return r.operador, r.cargado_por_user_id


def test_perfil_y_permisos():
    from app.user_roles import ROLE_LABELS, role_template_perm_sets, user_is_responsable_laboratorio

    view, edit = role_template_perm_sets("responsable_laboratorio")
    for p in ("salmuera", "reactor", "agua", "stock_ingreso_mp", "stock_ingreso_lab", "stock_consumos",
              "entregas_cargar", "entregas_programar", "entregas_entregar", "lab_reactivos"):
        assert p in edit, p
    assert ROLE_LABELS["responsable_laboratorio"] == "Responsable de laboratorio"

    class U:
        is_admin = False
        rol = "responsable_laboratorio"

    assert user_is_responsable_laboratorio(U())


def test_carga_analisis_sin_turno_y_con_turno(app, lab):
    client, (lab_id, oper_id) = lab
    from app.models import User
    from app.services import shift_handover_service as sh

    with app.app_context():
        from app.extensions import db

        assert sh.user_participates_operational_shift(db.session.get(User, lab_id)) is False

    # Sin turno abierto: puede cargar igual; queda a su nombre marcado «(sin turno)».
    r = client.post("/produccion/agua", data={"numero_columna": "1", "temperatura": "25", "dureza": "3"})
    assert r.status_code in (302, 303)
    assert _ultimo_agua(app) == ("Laura Lab (sin turno)", lab_id)

    # Con el turno de Oscar abierto: el responsable es el operador; ella queda como «cargado por».
    _abrir_turno(app, oper_id)
    r = client.post("/produccion/agua", data={"numero_columna": "2", "temperatura": "26", "dureza": "4"})
    assert r.status_code in (302, 303)
    assert _ultimo_agua(app) == ("Oscar Operador", lab_id)


def test_no_registra_paradas_y_puede_ajustar_stock(app, lab):
    client, _ = lab
    r = client.post("/produccion/parada-planta", json={"circuit_key": "agua", "action": "start"})
    assert r.status_code == 403 and "operador de turno" in r.get_json()["error"]
    page = client.get("/produccion/stock/ajustes", follow_redirects=True).get_data(as_text=True)
    assert "Solo administradores" not in page
