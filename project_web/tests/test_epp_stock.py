from __future__ import annotations

import re

from werkzeug.security import generate_password_hash


def _cliente(app, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-stk"), activo=True, is_admin=False, **kw))
        db.session.commit()
    c = app.test_client()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', c.get("/login").get_data(as_text=True)).group(1)
    assert c.post("/login", data={"username": username, "password": "pw-stk", "csrf_token": tok}).status_code in (302, 303)
    return c


def _items(app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEppItem, User
    from app.services import personal_service as ps

    with app.app_context():
        ps.sync_empleados_from_users()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        emp.dni, emp.puesto = "30333000", "Operador"
        pant = PersonalEppItem(nombre="Pantalón stock test", categoria="ropa", activo=True, stock_por_talle=True, stock_minimo=2)
        casco = PersonalEppItem(nombre="Casco stock test", categoria="epp", activo=True, stock_por_talle=False)
        db.session.add_all([pant, casco])
        db.session.commit()
        return emp.id, pant.id, casco.id


def _entregar(client, emp_id, item_id, talle="", cantidad=1):
    return client.post("/personal/epp/entregas", data={
        "empleado_id": str(emp_id), "item_id": str(item_id), "fecha": "2026-10-06", "talle": talle, "cantidad": str(cantidad),
        "tipo_modelo": "X", "marca": "Y", "certificacion": "SI", "epp_asignados": str(item_id)}, follow_redirects=True)


def test_ingreso_conteo_y_entregas_descuentan(app, auth_client):
    from app.services import epp_stock_service as stk

    emp_id, pant, casco = _items(app)
    lab = _cliente(app, "pytest_lab_stk", rol="responsable_laboratorio")
    html = lab.get("/personal/epp/stock").get_data(as_text=True)
    assert "Stock de ropa y EPP" in html and "Conteo físico" in html and "Solo lectura en UI" not in html

    # Conteo inicial y compra.
    assert "ajuste de +3" in lab.post("/personal/epp/stock", data={"accion": "conteo", "item_id": str(pant), "talle": "42", "contado": "3"}, follow_redirects=True).get_data(as_text=True)
    assert "indicá el talle" in lab.post("/personal/epp/stock", data={"accion": "ingreso", "item_id": str(pant), "cantidad": "5"}, follow_redirects=True).get_data(as_text=True)
    lab.post("/personal/epp/stock", data={"accion": "ingreso", "item_id": str(pant), "talle": "44", "cantidad": "5", "proveedor": "Proveedor X"})
    lab.post("/personal/epp/stock", data={"accion": "ingreso", "item_id": str(casco), "talle": "M", "cantidad": "2"})
    with app.app_context():
        assert (stk.saldo(pant, "42"), stk.saldo(pant, "44"), stk.saldo(casco, "")) == (3, 5, 2)

    # Cada entrega descuenta sola (talle normalizado); sin stock deja registrar y avisa.
    _entregar(auth_client, emp_id, pant, talle=" 42 ", cantidad=2)
    r = _entregar(auth_client, emp_id, casco, talle="L", cantidad=3)
    assert "no había stock suficiente de Casco stock test (había 2)" in r.get_data(as_text=True)
    with app.app_context():
        assert (stk.saldo(pant, "42"), stk.saldo(casco, "")) == (1, -1)
        filas = {r["item"].id: r for r in stk.resumen()}
        assert filas[pant]["total"] == 6 and filas[pant]["talles"] == [("42", 1), ("44", 5)]
        assert filas[casco]["negativo"] is True

    # Un conteo corrige: había -1 en el sistema y en el depósito hay 0.
    lab.post("/personal/epp/stock", data={"accion": "conteo", "item_id": str(casco), "contado": "0"})
    with app.app_context():
        assert stk.saldo(casco, "") == 0
    pagina = lab.get("/personal/epp/stock").get_data(as_text=True)
    assert "42: 1" in pagina and "44: 5" in pagina and "Ajuste por conteo" in pagina


def test_sin_aviso_antes_de_empezar_y_permisos(app, auth_client):
    emp_id, pant, _ = _items(app)
    r = _entregar(auth_client, emp_id, pant, talle="40")
    assert "no había stock" not in r.get_data(as_text=True)
    oper = _cliente(app, "pytest_oper_stk", rol="operaciones")
    # Ve el stock (tiene acceso a stock) pero no carga.
    assert oper.get("/personal/epp/stock").status_code == 200
    r = oper.post("/personal/epp/stock", data={"accion": "ingreso", "item_id": str(pant), "talle": "40", "cantidad": "9"}, follow_redirects=True)
    assert "Solo la responsable de laboratorio" in r.get_data(as_text=True)
