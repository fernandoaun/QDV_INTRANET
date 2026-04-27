from __future__ import annotations

import re


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_operations_can_logout_without_closing_shift_for_shared_computer(app, client):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import ShiftSession, User
    from app.user_roles import ROLE_MANTENIMIENTO, ROLE_OPERACIONES

    with app.app_context():
        op = User(
            username="pytest_ops_shared_pc",
            password_hash=generate_password_hash("ops-secret"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        mant = User(
            username="pytest_mant_shared_pc",
            password_hash=generate_password_hash("mant-secret"),
            is_admin=False,
            activo=True,
            rol=ROLE_MANTENIMIENTO,
        )
        db.session.add_all([op, mant])
        db.session.flush()
        shift = ShiftSession(
            user_id=int(op.id),
            effective_role=ROLE_OPERACIONES,
            started_at_iso="2026-04-27T08:00:00",
            ended_at_iso=None,
            status="open",
            created_at_iso="2026-04-27T08:00:00",
            updated_at_iso="2026-04-27T08:00:00",
        )
        db.session.add(shift)
        db.session.commit()
        shift_id = int(shift.id)

    login_page = client.get("/login")
    assert login_page.status_code == 200
    login_resp = client.post(
        "/login",
        data={
            "username": "pytest_ops_shared_pc",
            "password": "ops-secret",
            "csrf_token": _csrf(login_page.get_data(as_text=True)),
        },
        follow_redirects=False,
    )
    assert login_resp.status_code in (302, 303)

    logout_question = client.get("/operacion/turno/salir-pregunta")
    assert logout_question.status_code == 200
    assert "mantener turno abierto" in logout_question.get_data(as_text=True)

    logout_resp = client.post(
        "/operacion/turno/salir-pregunta",
        data={
            "choice": "mantener",
            "csrf_token": _csrf(logout_question.get_data(as_text=True)),
        },
        follow_redirects=False,
    )
    assert logout_resp.status_code in (302, 303)
    assert logout_resp.headers["Location"].endswith("/login")

    with client.session_transaction() as sess:
        assert "user_id" not in sess

    with app.app_context():
        persisted = db.session.get(ShiftSession, shift_id)
        assert persisted is not None
        assert persisted.status == "open"
        assert persisted.ended_at_iso is None

    mant_login_page = client.get("/login")
    assert mant_login_page.status_code == 200
    mant_login_resp = client.post(
        "/login",
        data={
            "username": "pytest_mant_shared_pc",
            "password": "mant-secret",
            "csrf_token": _csrf(mant_login_page.get_data(as_text=True)),
        },
        follow_redirects=False,
    )
    assert mant_login_resp.status_code in (302, 303)

    produccion = client.get("/produccion/")
    assert produccion.status_code == 200
    assert "Producción" in produccion.get_data(as_text=True)

    with app.app_context():
        persisted = db.session.get(ShiftSession, shift_id)
        assert persisted is not None
        assert persisted.status == "open"
        assert persisted.ended_at_iso is None
