from __future__ import annotations

import re

import pytest


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    return m.group(1)


def _login(client, username: str, password: str) -> None:
    page = client.get("/login")
    r = client.post("/login", data={"username": username, "password": password, "csrf_token": _csrf(page.get_data(as_text=True))})
    assert r.status_code in (302, 303)


@pytest.fixture
def turno_abierto(app):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import ShiftSession, User
    from app.user_roles import ROLE_OPERACIONES, ROLE_RESPONSABLE_LABORATORIO

    with app.app_context():
        op = User(username="pt_op_olvido", password_hash=generate_password_hash("x1"), is_admin=False, activo=True, rol=ROLE_OPERACIONES)
        op2 = User(username="pt_op_sig", password_hash=generate_password_hash("x2"), is_admin=False, activo=True, rol=ROLE_OPERACIONES)
        lab = User(username="pt_lucia", nombre_completo="Lucía Test", password_hash=generate_password_hash("x3"), is_admin=False, activo=True, rol=ROLE_RESPONSABLE_LABORATORIO)
        db.session.add_all([op, op2, lab])
        db.session.flush()
        s = ShiftSession(user_id=int(op.id), effective_role=ROLE_OPERACIONES, started_at_iso="2026-10-07T16:50:24",
                         status="open", created_at_iso="2026-10-07T16:50:24", updated_at_iso="2026-10-07T16:50:24")
        db.session.add(s)
        db.session.commit()
        return {"session_id": int(s.id), "op_id": int(op.id)}


def test_responsable_laboratorio_cierra_turno_olvidado(app, client, turno_abierto):
    from app.extensions import db
    from app.models import ShiftHandover, ShiftSession

    _login(client, "pt_lucia", "x3")
    assert "Cerrar turno olvidado" in client.get("/dashboard").get_data(as_text=True)
    page = client.get("/operacion/turno/cerrar-olvidado")
    assert page.status_code == 200
    r = client.post("/operacion/turno/cerrar-olvidado", data={
        "csrf_token": _csrf(page.get_data(as_text=True)),
        "hypochlorite_stock_liters": "12500", "motivo": "Se fue sin entregar", "confirmar": "1",
    })
    assert r.status_code in (302, 303)
    with app.app_context():
        s = db.session.get(ShiftSession, turno_abierto["session_id"])
        assert s.status == "closed" and s.ended_at_iso
        ho = db.session.query(ShiftHandover).filter_by(shift_session_id=s.id).one()
        assert ho.status == "pending_reception"
        assert ho.outgoing_user_id == turno_abierto["op_id"]
        assert ho.hypochlorite_stock_liters == 12500
        assert "Lucía Test" in ho.closing_notes and "Se fue sin entregar" in ho.closing_notes


def test_cierre_exige_stock_y_confirmacion(app, client, turno_abierto):
    from app.extensions import db
    from app.models import ShiftSession

    _login(client, "pt_lucia", "x3")
    page = client.get("/operacion/turno/cerrar-olvidado")
    client.post("/operacion/turno/cerrar-olvidado", data={"csrf_token": _csrf(page.get_data(as_text=True)), "motivo": "x", "confirmar": "1"})
    client.post("/operacion/turno/cerrar-olvidado", data={"csrf_token": _csrf(page.get_data(as_text=True)), "hypochlorite_stock_liters": "100", "motivo": "x"})
    with app.app_context():
        assert db.session.get(ShiftSession, turno_abierto["session_id"]).status == "open"


def test_operador_no_puede_cerrar_turno_ajeno(app, client, turno_abierto):
    from app.extensions import db
    from app.models import ShiftSession

    _login(client, "pt_op_sig", "x2")
    r = client.get("/operacion/turno/cerrar-olvidado")
    assert r.status_code in (302, 303)
    r = client.post("/operacion/turno/cerrar-olvidado", data={"hypochlorite_stock_liters": "1", "motivo": "x", "confirmar": "1"})
    with app.app_context():
        assert db.session.get(ShiftSession, turno_abierto["session_id"]).status == "open"


def test_el_siguiente_operador_recepciona_el_turno_cerrado(app, client, turno_abierto):
    from app.extensions import db
    from app.models import ShiftSession, User
    from app.services import shift_handover_service as sh

    with app.app_context():
        lab = db.session.query(User).filter_by(username="pt_lucia").one()
        s = db.session.get(ShiftSession, turno_abierto["session_id"])
        ho = sh.persist_forced_handover({"hypochlorite_stock_liters": "900", "motivo": "olvido", "confirmar": "1"}, lab, s, "2026-10-08T07:00:00")
        hid = int(ho.id)
    _login(client, "pt_op_sig", "x2")
    page = client.get(f"/operacion/turno/recibir/{hid}")
    assert page.status_code == 200
    r = client.post(f"/operacion/turno/recibir/{hid}", data={
        "csrf_token": _csrf(page.get_data(as_text=True)), "confirm_read": "1",
        "reception_mode": "accepted", "with_laboratorist": "no",
    })
    assert r.status_code in (302, 303)
    with app.app_context():
        nuevo = sh.get_open_shift_session()
        assert nuevo is not None and nuevo.user.username == "pt_op_sig"
