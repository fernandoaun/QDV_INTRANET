from __future__ import annotations


def test_personal_hub_ok(auth_client):
    r = auth_client.get("/personal/", follow_redirects=True)
    assert r.status_code == 200
    assert b"Personal" in r.data


def test_personal_blocked_nonprivileged(mant_client):
    r = mant_client.get("/personal/", follow_redirects=False)
    assert r.status_code in (302, 303)


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
