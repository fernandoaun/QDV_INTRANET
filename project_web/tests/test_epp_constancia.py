from __future__ import annotations


def _emp_item(app, nombre_item="Botines test", categoria="epp"):
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEppItem, User
    from app.services import personal_service as ps

    with app.app_context():
        ps.sync_empleados_from_users()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        emp.dni = "30111222"
        emp.puesto = "Operador de planta"
        item = PersonalEppItem(nombre=nombre_item, categoria=categoria, activo=True)
        db.session.add(item)
        db.session.commit()
        return emp.id, item.id


def test_constancia_con_entrega_firma_por_confirmacion(auth_client, app):
    emp_id, item_id = _emp_item(app)
    r = auth_client.post(
        "/personal/epp/entregas",
        data={
            "empleado_id": str(emp_id),
            "item_id": str(item_id),
            "fecha": "2026-09-10",
            "talle": "42",
            "cantidad": "1",
            "tipo_modelo": "Puntera de acero",
            "marca": "Funcional",
            "certificacion": "si",
        },
    )
    assert r.status_code in (302, 303)

    html = auth_client.get(f"/personal/epp/constancia/{emp_id}").get_data(as_text=True)
    assert "Resolución 299/11, Anexo I" in html and "30-70860737-8" in html and "30111222" in html
    assert "Botines test (talle 42)" in html and "Puntera de acero" in html and "Funcional" in html
    assert ">SI<" in html and "10/09/2026" in html
    assert "Pendiente de confirmación" in html
    # Sin descripción cargada se usa el puesto del legajo.
    assert "Operador de planta" in html

    with app.app_context():
        from app.services import personal_service as ps

        entrega_id = ps.list_entregas_epp_pendientes_empleado(emp_id)[0].id
    auth_client.post("/personal/mis-entregas-epp", data={"entrega_id": str(entrega_id), "confirmar_recepcion": "1"})
    html = auth_client.get(f"/personal/epp/constancia/{emp_id}").get_data(as_text=True)
    assert "Confirmado por el trabajador" in html and "Pendiente de confirmación" not in html


def test_constancia_encabezado_se_carga_una_vez(auth_client, app):
    emp_id, item_id = _emp_item(app, "Antiparras test")
    r = auth_client.post(
        f"/personal/epp/constancia/{emp_id}",
        data={"epp_descripcion_puesto": "Operación de celdas y carga de camiones", "epp_asignados": [str(item_id), "99999"]},
    )
    assert r.status_code in (302, 303)
    html = auth_client.get(f"/personal/epp/constancia/{emp_id}").get_data(as_text=True)
    assert "Operación de celdas y carga de camiones" in html and "<b>Antiparras test</b>" in html

    # Desmarcar deja la lista vacía.
    auth_client.post(f"/personal/epp/constancia/{emp_id}", data={"epp_descripcion_puesto": ""})
    with app.app_context():
        from app.models import EmpleadoPersonal
        from app.services import epp_constancia_service as cs
        from app.extensions import db

        assert cs.asignados(db.session.get(EmpleadoPersonal, emp_id)) == []


def test_constancia_en_blanco_y_registro_sgi(auth_client, app):
    html = auth_client.get("/personal/epp/constancia/en-blanco").get_data(as_text=True)
    assert "CONSTANCIA DE ENTREGA EPP" in html and "Quimica del Valle SRL." in html
    assert "Firma del trabajador" in html and "Datos de la constancia" not in html

    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        links = proc.registro_modulo_links("epp_constancia")
    assert links["blank_url"] == "/personal/epp/constancia/en-blanco"
    assert links["filled_url"] == "/personal/epp/entregas"
