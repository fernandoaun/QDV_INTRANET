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
            "epp_asignados": str(item_id),
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


def test_entrega_exige_todos_los_datos_de_la_planilla(auth_client, app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEntregaEpp
    from app.services import epp_constancia_service as cs

    emp_id, item_id = _emp_item(app, "Casco test")
    with app.app_context():
        emp = db.session.get(EmpleadoPersonal, emp_id)
        emp.dni = ""
        emp.puesto = ""
        db.session.commit()
    base = {"empleado_id": str(emp_id), "item_id": str(item_id), "fecha": "2026-09-12", "cantidad": "1"}

    r = auth_client.post("/personal/epp/entregas", data=base, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "falta" in html and "tipo / modelo" in html and "DNI del trabajador" in html and "EPP asignados" in html
    with app.app_context():
        assert db.session.query(PersonalEntregaEpp).filter_by(empleado_id=emp_id).count() == 0

    completo = {**base, "tipo_modelo": "Clase B", "marca": "3M", "certificacion": "NO",
                "emp_dni": "27333444", "epp_descripcion_puesto": "Mantenimiento eléctrico", "epp_asignados": str(item_id)}
    assert auth_client.post("/personal/epp/entregas", data=completo).status_code in (302, 303)
    with app.app_context():
        emp = db.session.get(EmpleadoPersonal, emp_id)
        assert emp.dni == "27333444" and emp.epp_descripcion_puesto == "Mantenimiento eléctrico"
        assert [i.id for i in cs.asignados(emp)] == [item_id]

    # Una vez cargados, los datos del trabajador ya no se piden.
    segunda = {**base, "fecha": "2026-09-20", "tipo_modelo": "Clase B", "marca": "3M", "certificacion": "NO"}
    item2 = None
    with app.app_context():
        from app.models import PersonalEppItem

        it = PersonalEppItem(nombre="Protector auditivo test", categoria="otro", activo=True)
        db.session.add(it)
        db.session.commit()
        item2 = it.id
    segunda["item_id"] = str(item2)
    assert auth_client.post("/personal/epp/entregas", data=segunda).status_code in (302, 303)
    with app.app_context():
        assert db.session.query(PersonalEntregaEpp).filter_by(empleado_id=emp_id).count() == 2

    page = auth_client.get("/personal/epp/entregas").get_data(as_text=True)
    assert 'name="tipo_modelo" maxlength="128" required' in page and "Datos del trabajador para la constancia" in page


def test_pestania_epp_del_legajo_pide_los_datos(auth_client, app):
    from app.extensions import db
    from app.models import EmpleadoPersonal

    emp_id, item_id = _emp_item(app, "Guantes test")
    with app.app_context():
        db.session.get(EmpleadoPersonal, emp_id).dni = ""
        db.session.commit()
    html = auth_client.get(f"/personal/legajos/{emp_id}?tab=epp").get_data(as_text=True)
    assert 'name="marca" maxlength="128" required' in html and 'name="emp_dni"' in html
    r = auth_client.post(
        f"/personal/legajos/{emp_id}",
        data={"action": "entrega_epp", "tab": "epp", "item_id": str(item_id), "fecha": "2026-09-15", "cantidad": "2",
              "tipo_modelo": "Nitrilo", "marca": "Ansell", "certificacion": "SI", "emp_dni": "28999000",
              "epp_asignados": [str(item_id)]},
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        emp = db.session.get(EmpleadoPersonal, emp_id)
        assert emp.dni == "28999000" and emp.entregas_epp.count() == 1
