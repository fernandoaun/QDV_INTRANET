from __future__ import annotations

import re

from werkzeug.security import generate_password_hash


def _cliente(app, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-ped"), activo=True, is_admin=False, **kw))
        db.session.commit()
    c = app.test_client()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', c.get("/login").get_data(as_text=True)).group(1)
    assert c.post("/login", data={"username": username, "password": "pw-ped", "csrf_token": tok}).status_code in (302, 303)
    return c


def _empleado_e_item(app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEppItem, User
    from app.services import personal_service as ps

    with app.app_context():
        ps.sync_empleados_from_users()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        emp.dni, emp.puesto = "30111000", "Operador"
        item = PersonalEppItem(nombre="Guantes pedido test", categoria="epp", activo=True)
        db.session.add(item)
        db.session.commit()
        return emp.id, item.id


def _pedir(client, item_id, **extra):
    data = {"accion": "pedir_epp", "item_id": str(item_id), "talle": "9", "cantidad": "2", "motivo": "rotura"} | extra
    return client.post("/personal/mis-entregas-epp", data=data, follow_redirects=True)


def test_empleado_pide_y_responsable_entrega(auth_client, app):
    from app.extensions import db
    from app.models import PersonalSolicitudEpp

    emp_id, item_id = _empleado_e_item(app)
    html = auth_client.get("/personal/mis-entregas-epp").get_data(as_text=True)
    assert "Pedir ropa / EPP" in html and "Guantes pedido test" in html
    r = _pedir(auth_client, item_id, comentario="Se rompieron en la carga")
    assert "Pedido enviado a la responsable de laboratorio" in r.get_data(as_text=True)
    with app.app_context():
        sol = db.session.query(PersonalSolicitudEpp).one()
        assert (sol.empleado_id, sol.cantidad, sol.talle, sol.estado) == (emp_id, 2, "9", "pendiente")
        sol_id = sol.id

    lab = _cliente(app, "pytest_lab_ped", rol="responsable_laboratorio", nombre_completo="Lucía Lab")
    pedidos = lab.get("/personal/epp/pedidos").get_data(as_text=True)
    assert "Guantes pedido test" in pedidos and "Entregar" in pedidos
    # Ella entra a lo de EPP, pero no al resto de Personal.
    assert lab.get("/personal/", follow_redirects=False).status_code in (302, 303)
    form = lab.get(f"/personal/epp/entregas?solicitud_id={sol_id}").get_data(as_text=True)
    assert "Entregando el pedido" in form and f'name="solicitud_id" value="{sol_id}"' in form

    r = lab.post(
        "/personal/epp/entregas",
        data={"solicitud_id": str(sol_id), "empleado_id": str(emp_id), "item_id": str(item_id), "fecha": "2026-10-02",
              "talle": "9", "cantidad": "2", "tipo_modelo": "Nitrilo", "marca": "Ansell", "certificacion": "SI",
              "epp_asignados": str(item_id)},
    )
    assert r.status_code in (302, 303) and r.headers["Location"].endswith("/personal/epp/pedidos")
    with app.app_context():
        sol = db.session.get(PersonalSolicitudEpp, sol_id)
        assert sol.estado == "entregada" and sol.entrega_id is not None


def test_rechazo_y_cancelacion(auth_client, app):
    from app.extensions import db
    from app.models import PersonalSolicitudEpp

    _, item_id = _empleado_e_item(app)
    _pedir(auth_client, item_id)
    _pedir(auth_client, item_id, motivo="otro", comentario="Para el depósito")
    assert "Contá brevemente" in _pedir(auth_client, item_id, motivo="otro").get_data(as_text=True)
    with app.app_context():
        a, b = [s.id for s in db.session.query(PersonalSolicitudEpp).order_by(PersonalSolicitudEpp.id)]

    lab = _cliente(app, "pytest_lab_ped2", rol="responsable_laboratorio")
    assert "Escribí el motivo" in lab.post("/personal/epp/pedidos", data={"solicitud_id": str(a)}, follow_redirects=True).get_data(as_text=True)
    lab.post("/personal/epp/pedidos", data={"solicitud_id": str(a), "respuesta": "Ya se te entregaron la semana pasada"})
    auth_client.post("/personal/mis-entregas-epp", data={"accion": "cancelar_pedido", "solicitud_id": str(b)})
    with app.app_context():
        sa, sb = db.session.get(PersonalSolicitudEpp, a), db.session.get(PersonalSolicitudEpp, b)
        assert (sa.estado, sa.respuesta) == ("rechazada", "Ya se te entregaron la semana pasada")
        assert sb.estado == "cancelada"
    mis = auth_client.get("/personal/mis-entregas-epp").get_data(as_text=True)
    assert "Rechazada" in mis and "Ya se te entregaron la semana pasada" in mis and "Cancelada" in mis


def test_operador_no_ve_los_pedidos(app):
    oper = _cliente(app, "pytest_oper_ped", rol="operaciones")
    assert oper.get("/personal/epp/pedidos", follow_redirects=False).status_code in (302, 303)


def test_destinatario_es_la_responsable_de_laboratorio(app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, User
    from app.services import epp_pedidos_service as svc

    with app.app_context():
        u = User(username="pytest_lab_mail", password_hash="x", activo=True, is_admin=False, rol="responsable_laboratorio")
        db.session.add(u)
        db.session.flush()
        db.session.add(EmpleadoPersonal(user_id=u.id, legajo="L-MAIL-1", apellido="Lab", nombre="Lucía", email="lucia@example.com"))
        db.session.commit()
        assert svc.destinatarios_responsables(app) == ["lucia@example.com"]


def test_pantallas_editables_para_empleado_y_responsable(app):
    """La sección Personal es solo lectura para quien no administra legajos: estas pantallas no."""
    from app.auth_utils import user_can_edit_endpoint
    from app.extensions import db
    from app.models import User

    with app.app_context(), app.test_request_context():
        oper = User(username="pytest_ed_oper", password_hash="x", activo=True, is_admin=False, rol="operaciones")
        lab = User(username="pytest_ed_lab", password_hash="x", activo=True, is_admin=False, rol="responsable_laboratorio")
        db.session.add_all([oper, lab])
        db.session.commit()
        assert user_can_edit_endpoint(oper, "personal.mis_entregas_epp") is True
        assert user_can_edit_endpoint(oper, "personal.epp_pedidos") is False
        for ep in ("personal.epp_entregas", "personal.epp_pedidos", "personal.epp_constancia", "personal.mis_entregas_epp"):
            assert user_can_edit_endpoint(lab, ep) is True, ep
        assert user_can_edit_endpoint(lab, "personal.legajo_detalle") is False


def test_formulario_de_pedido_no_queda_deshabilitado(app):
    """El script de solo lectura de base.html no debe estar en «Mis entregas EPP» para un operador."""
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEppItem, User

    c = _cliente(app, "pytest_ped_form", rol="operaciones")
    with app.app_context():
        u = db.session.query(User).filter_by(username="pytest_ped_form").one()
        if db.session.query(EmpleadoPersonal).filter_by(user_id=u.id).first() is None:
            db.session.add(EmpleadoPersonal(user_id=u.id, legajo="L-FORM-1", apellido="Op", nombre="Test"))
        db.session.add(PersonalEppItem(nombre="Casco form test", categoria="epp", activo=True))
        db.session.commit()
    html = c.get("/personal/mis-entregas-epp").get_data(as_text=True)
    assert "Pedir ropa / EPP" in html
    assert "Solo lectura en UI" not in html
