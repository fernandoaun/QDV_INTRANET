from __future__ import annotations


def test_personal_hub_ok(auth_client):
    r = auth_client.get("/personal/", follow_redirects=True)
    assert r.status_code == 200
    assert b"Personal" in r.data


def test_personal_blocked_nonprivileged(mant_client):
    r = mant_client.get("/personal/", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_ensure_default_epp_catalog_seeds_ropa_y_epp(app):
    from app.services import personal_service as ps

    with app.app_context():
        created = ps.ensure_default_epp_catalog()
        assert created == len(ps.DEFAULT_EPP_CATALOG)
        cats = {it.categoria for it in ps.list_epp_items()}
        assert "ropa" in cats
        assert "epp" in cats
        assert ps.ensure_default_epp_catalog() == 0


def test_epp_entregas_page_seeds_catalog(auth_client):
    r = auth_client.get("/personal/epp/entregas")
    assert r.status_code == 200
    assert b"Pantal" in r.data
    assert b"Casco" in r.data
    assert b"Registrar" in r.data


def test_registrar_entrega_ropa_y_epp(auth_client, app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, User
    from app.services import personal_service as ps

    with app.app_context():
        ps.sync_empleados_from_users()
        ps.ensure_default_epp_catalog()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        ropa = next(it for it in ps.list_epp_items(solo_activos=True) if it.categoria == "ropa")
        epp = next(it for it in ps.list_epp_items(solo_activos=True) if it.categoria == "epp")
        emp_id = emp.id
        ropa_id = ropa.id
        epp_id = epp.id

    for item_id, label in ((ropa_id, "ropa"), (epp_id, "epp")):
        r = auth_client.post(
            "/personal/epp/entregas",
            data={
                "empleado_id": str(emp_id),
                "item_id": str(item_id),
                "fecha": "2026-06-18",
                "talle": "M",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303), label

    with app.app_context():
        pendientes = ps.list_entregas_epp_pendientes_empleado(emp_id)
        assert len(pendientes) == 2


def test_personal_post_forms_include_csrf(auth_client):
    """En producción CSRF está activo; los formularios POST de Personal deben incluir el token."""
    for path in ("/personal/epp/catalogo", "/personal/epp/entregas", "/personal/vacaciones"):
        r = auth_client.get(path)
        assert r.status_code == 200
        assert b'name="csrf_token"' in r.data, path


def test_personal_legajo_crud(auth_client):
    r = auth_client.get("/personal/legajos/nuevo", follow_redirects=True)
    assert r.status_code == 200
    assert b"usuario" in r.data.lower()

    r = auth_client.get("/personal/legajos")
    assert r.status_code == 200
    assert b"pytest_admin" in r.data

    r = auth_client.get("/personal/legajos?q=pytest")
    assert r.status_code == 200
    assert b"pytest_admin" in r.data

    r = auth_client.post(
        "/personal/epp/catalogo",
        data={"nombre": "Guantes nitrilo", "categoria": "epp", "requiere_talle": "1", "activo": "1"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    r = auth_client.get("/personal/epp/catalogo")
    assert b"Guantes nitrilo" in r.data

    r = auth_client.get("/personal/vacaciones")
    assert r.status_code == 200


def test_entrega_epp_workflow_devolucion_y_confirmacion(auth_client, app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEppItem, User
    from app.services import personal_service as ps

    with app.app_context():
        ps.sync_empleados_from_users()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        item = PersonalEppItem(nombre="Pantalón test wf", categoria="ropa", activo=True)
        db.session.add(item)
        db.session.commit()
        emp_id = emp.id
        item_id = item.id
        admin_id = admin.id

    r = auth_client.post(
        "/personal/epp/entregas",
        data={
            "empleado_id": str(emp_id),
            "item_id": str(item_id),
            "fecha": "2026-06-01",
            "talle": "42",
            "cantidad": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        pendientes = ps.list_entregas_epp_pendientes_empleado(emp_id)
        assert len(pendientes) == 1
        primera_id = pendientes[0].id

    r = auth_client.post(
        "/personal/mis-entregas-epp",
        data={"entrega_id": str(primera_id), "confirmar_recepcion": "1"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        primera = ps.ultima_entrega_confirmada_empleado_item(emp_id, item_id)
        assert primera is not None
        assert primera.estado == "confirmada"

    r = auth_client.post(
        "/personal/epp/entregas",
        data={
            "empleado_id": str(emp_id),
            "item_id": str(item_id),
            "fecha": "2026-06-18",
            "talle": "44",
            "cantidad": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        pendientes = ps.list_entregas_epp_pendientes_empleado(emp_id)
        assert len(pendientes) == 0

    r = auth_client.post(
        "/personal/epp/entregas",
        data={
            "empleado_id": str(emp_id),
            "item_id": str(item_id),
            "fecha": "2026-06-18",
            "talle": "44",
            "cantidad": "1",
            "prenda_anterior_devuelta": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        pendientes = ps.list_entregas_epp_pendientes_empleado(emp_id)
        assert len(pendientes) == 1
        entrega_id = pendientes[0].id

    r = auth_client.get("/personal/mis-entregas-epp")
    assert r.status_code == 200
    assert b"Pendientes de confirmaci" in r.data

    r = auth_client.post(
        "/personal/mis-entregas-epp",
        data={"entrega_id": str(entrega_id), "confirmar_recepcion": "1"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        from app.models import PersonalEntregaEpp

        entrega = db.session.get(PersonalEntregaEpp, entrega_id)
        assert entrega is not None
        assert entrega.estado == "confirmada"
        assert entrega.confirmada_by_user_id == admin_id
        assert ps.list_entregas_epp_pendientes_empleado(emp_id) == []


def test_entrega_epp_envia_aviso_mail_al_registrar(auth_client, app, monkeypatch):
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEppItem, User
    from app.services import personal_service as ps

    sent: list[dict] = []

    def _fake_mail(app, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr("app.services.personal_epp_reminder_service.enviar_mail", _fake_mail)
    monkeypatch.setattr("app.services.personal_epp_reminder_service.is_mail_fully_configured", lambda _app: True)

    with app.app_context():
        ps.sync_empleados_from_users()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        emp.email = "empleado@test.example"
        item = PersonalEppItem(nombre="Casco test mail", categoria="epp", activo=True)
        db.session.add(item)
        db.session.commit()
        emp_id = emp.id
        item_id = item.id

    r = auth_client.post(
        "/personal/epp/entregas",
        data={
            "empleado_id": str(emp_id),
            "item_id": str(item_id),
            "fecha": "2026-06-18",
            "talle": "M",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert len(sent) == 1
    assert sent[0]["destinatarios"] == ["empleado@test.example"]
    assert "Casco test mail" in sent[0]["asunto"]


def test_run_entrega_epp_reminders_agrupa_por_empleado(app, monkeypatch):
    from datetime import date, datetime, timedelta, timezone

    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEntregaEpp, PersonalEppItem
    from app.services.personal_epp_reminder_service import run_entrega_epp_reminders

    sent: list[dict] = []

    def _fake_mail(app, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr("app.services.personal_epp_reminder_service.enviar_mail", _fake_mail)
    monkeypatch.setattr("app.services.personal_epp_reminder_service.is_mail_fully_configured", lambda _app: True)

    with app.app_context():
        emp = EmpleadoPersonal(
            legajo="MAIL-1",
            apellido="Mail",
            nombre="Test",
            email="mail.test@example.com",
            fecha_ingreso=date(2026, 1, 1),
        )
        db.session.add(emp)
        db.session.flush()
        item1 = PersonalEppItem(nombre="Item mail 1", categoria="ropa", activo=True)
        item2 = PersonalEppItem(nombre="Item mail 2", categoria="epp", activo=True)
        db.session.add_all([item1, item2])
        db.session.flush()
        ayer = datetime.now(timezone.utc) - timedelta(days=1)
        db.session.add_all(
            [
                PersonalEntregaEpp(
                    empleado_id=emp.id,
                    item_id=item1.id,
                    fecha=date(2026, 6, 10),
                    estado="pendiente",
                    aviso_pendiente_at=ayer,
                ),
                PersonalEntregaEpp(
                    empleado_id=emp.id,
                    item_id=item2.id,
                    fecha=date(2026, 6, 12),
                    estado="pendiente",
                    aviso_pendiente_at=ayer,
                ),
            ]
        )
        db.session.commit()

        out = run_entrega_epp_reminders(app, dry_run=False)
        assert out["emails_sent"] == 1
        assert len(sent) == 1
        assert sent[0]["destinatarios"] == ["mail.test@example.com"]
        assert "2 entregas" in sent[0]["asunto"]


def test_entrega_epp_sin_devolucion_rechazada(auth_client, app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEppItem, User
    from app.services import personal_service as ps

    with app.app_context():
        ps.sync_empleados_from_users()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        item = PersonalEppItem(nombre="Camisa test wf", categoria="ropa", activo=True)
        db.session.add(item)
        db.session.commit()
        ok, _ = ps.save_entrega_epp(
            {"empleado_id": str(emp.id), "item_id": str(item.id), "fecha": "2026-05-01"},
            user_id=1,
        )
        assert ok is True
        pendiente = ps.entrega_epp_pendiente_empleado_item(emp.id, item.id)
        assert pendiente is not None
        ok_confirm, _ = ps.confirmar_entrega_epp(pendiente.id, user_id=emp.user_id)
        assert ok_confirm is True
        emp_id = emp.id
        item_id = item.id

    r = auth_client.post(
        "/personal/epp/entregas",
        data={
            "empleado_id": str(emp_id),
            "item_id": str(item_id),
            "fecha": "2026-06-18",
            "talle": "L",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        assert ps.list_entregas_epp_pendientes_empleado(emp_id) == []


def test_user_create_generates_legajo(auth_client, app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, User

    lg = auth_client.get("/login")
    html = lg.get_data(as_text=True)
    import re

    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = auth_client.post(
        "/admin/usuarios/nuevo",
        data={
            "username": "nuevo.emp",
            "nombre_completo": "Pérez, Ana",
            "password": "secret12",
            "password2": "secret12",
            "activo": "1",
            "rol": "operaciones",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        user = db.session.query(User).filter(User.username == "nuevo.emp").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == user.id).one()
        assert emp.apellido == "Pérez"
        assert emp.nombre == "Ana"
        assert emp.fecha_ingreso is not None
        import re
        assert re.fullmatch(r"\d{4}-\d{3}", emp.legajo)
        assert emp.legajo.startswith(str(emp.fecha_ingreso.year))
        user_id = user.id

    r = auth_client.get(f"/personal/legajos/usuario/{user_id}", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_legajo_completeness_indicator(app):
    from datetime import date

    from app.models import EmpleadoPersonal
    from app.services import personal_service as ps

    with app.app_context():
        emp = EmpleadoPersonal(
            legajo="T1",
            apellido="Test",
            nombre="User",
            dni="30123456",
            cuil="20-30123456-1",
            puesto="Operador",
            area="Planta",
            domicilio="Calle 1",
            telefono="123",
            email="a@b.com",
            talle_pantalon="42",
            talle_camisa="L",
            talle_calzado="41",
            talle_guantes="M",
            talle_mameluco="S",
        )
        assert ps.legajo_is_complete(emp) is False
        emp.fecha_nacimiento = date(1990, 1, 1)
        emp.fecha_ingreso = date(2020, 3, 1)
        assert ps.legajo_is_complete(emp) is True


def test_save_empleado_renumber_swapped_legajos_no_crash(app):
    """Renumerar no debe romper si los correlativos estaban invertidos (unique legajo)."""
    from datetime import date

    from app.extensions import db
    from app.models import EmpleadoPersonal
    from app.services import personal_service as ps

    with app.app_context():
        e1 = EmpleadoPersonal(
            legajo="2026-002",
            apellido="Primero",
            nombre="A",
            fecha_ingreso=date(2026, 1, 10),
        )
        e2 = EmpleadoPersonal(
            legajo="2026-001",
            apellido="Segundo",
            nombre="B",
            fecha_ingreso=date(2026, 6, 1),
        )
        db.session.add_all([e1, e2])
        db.session.commit()
        ok, msg, emp = ps.save_empleado(
            {
                "apellido": "Primero",
                "nombre": "A",
                "fecha_ingreso": "2026-01-10",
                "estado": "activo",
            },
            empleado_id=e1.id,
        )
        assert ok is True, msg
        assert emp is not None
        assert e1.legajo == "2026-001"
        assert e2.legajo == "2026-002"


def test_legajo_correlativo_por_anio(app):
    from datetime import date

    from app.extensions import db
    from app.models import EmpleadoPersonal
    from app.services import personal_service as ps

    with app.app_context():
        e1 = EmpleadoPersonal(
            legajo="TMP-1",
            apellido="Primero",
            nombre="A",
            fecha_ingreso=date(2026, 6, 1),
        )
        e2 = EmpleadoPersonal(
            legajo="TMP-2",
            apellido="Segundo",
            nombre="B",
            fecha_ingreso=date(2026, 1, 10),
        )
        db.session.add_all([e1, e2])
        db.session.flush()
        ps.renumber_legajos_for_year(2026)
        db.session.commit()
        assert e2.legajo == "2026-001"
        assert e1.legajo == "2026-002"


def test_users_list_shows_incomplete_legajo(auth_client):
    r = auth_client.get("/admin/usuarios")
    assert r.status_code == 200
    assert b"Incompleto" in r.data or b"Completo" in r.data
    assert b"Legajo RRHH" in r.data


def test_sgi_user_sin_legajo(auth_client, app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, User
    from app.user_roles import ROLE_SGI

    lg = auth_client.get("/login")
    html = lg.get_data(as_text=True)
    import re

    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = auth_client.post(
        "/admin/usuarios/nuevo",
        data={
            "username": "usuario.sgi",
            "nombre_completo": "SGI Test",
            "password": "secret12",
            "password2": "secret12",
            "activo": "1",
            "rol": ROLE_SGI,
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        user = db.session.query(User).filter(User.username == "usuario.sgi").one()
        assert db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == user.id).count() == 0

    r = auth_client.get("/admin/usuarios")
    assert b"usuario.sgi" in r.data
    assert b"N/A" in r.data

    r = auth_client.get("/personal/legajos")
    assert r.status_code == 200
    assert b"usuario.sgi" not in r.data


def test_mi_legajo_solo_lectura(auth_client, app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, User
    from app.services import personal_service as ps

    with app.app_context():
        ps.sync_empleados_from_users()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        emp.dni = "12345678"
        emp.fecha_nacimiento = __import__("datetime").date(1990, 1, 1)
        db.session.commit()

    r = auth_client.get("/personal/mi-legajo")
    assert r.status_code == 200
    assert b"Mi legajo" in r.data
    assert b"Solo lectura" in r.data
    assert b"Editar datos" not in r.data
    assert b"12345678" in r.data


def test_cumpleanos_hoy_y_banner(auth_client, app):
    from datetime import date

    from app.extensions import db
    from app.models import EmpleadoPersonal, User
    from app.services import personal_service as ps

    with app.app_context():
        ps.sync_empleados_from_users()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        hoy = ps.today_operacion()
        emp.fecha_nacimiento = date(1985, hoy.month, hoy.day)
        emp.estado = "activo"
        db.session.commit()
        assert len(ps.cumpleanos_hoy()) >= 1

    r = auth_client.get("/")
    assert r.status_code == 200
    assert b"cumplea" in r.data.lower()


def test_birthday_reminders_dry_run(app, admin_user):
    from datetime import date

    from app.extensions import db
    from app.models import EmpleadoPersonal, User
    from app.services import personal_service as ps
    from app.services.personal_birthday_reminder_service import run_birthday_reminders

    with app.app_context():
        ps.sync_empleados_from_users()
        admin = db.session.query(User).filter(User.username == "pytest_admin").one()
        emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
        hoy = ps.today_operacion()
        emp.fecha_nacimiento = date(1985, hoy.month, hoy.day)
        emp.email = "cumple@test.local"
        emp.estado = "activo"
        db.session.commit()
        out = run_birthday_reminders(app, dry_run=True)
        assert out["cumpleaneros"] >= 1
