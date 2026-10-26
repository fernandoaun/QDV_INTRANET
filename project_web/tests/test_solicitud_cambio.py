from __future__ import annotations

import re
from datetime import date

import pytest
from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-sc"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-sc", "csrf_token": tok}).status_code in (302, 303)
    return client


@pytest.fixture
def solicitud_id(app):
    from app.extensions import db
    from app.services import solicitud_cambio_service as svc

    with app.app_context():
        s, errs = svc.crear(
            {"asunto": "Cambio de bomba dosificadora", "fecha": "20/10/2026", "solicita": "Solicitante A", "prioridad": "alta",
             "tipos": ["Operativo", "Diseño"], "acciones_control": [{"actividad": "Probar la bomba", "fecha": "2026-11-05"}]},
            None,
        )
        assert not errs
        db.session.commit()
        assert s.numero == 1 and s.prioridad == "Alta" and s.tipos == "Operativo\nDiseño"
        assert svc.acciones(s) == [{"actividad": "Probar la bomba", "responsable": "", "fecha": "05/11/2026", "eficacia": ""}]
        return s.id


def test_listado_hoja_y_en_blanco(app, client, solicitud_id):
    c = _login(app, client, "pytest_sc_admin", is_admin=True, rol="operaciones")
    html = c.get("/sgi/solicitudes-cambio/").get_data(as_text=True)
    for txt in ("QDV-RG-PG-03_01", "Cambio de bomba dosificadora", "20/10/2026", "Nueva solicitud"):
        assert txt in html, txt
    hoja = c.get(f"/sgi/solicitudes-cambio/{solicitud_id}").get_data(as_text=True)
    for txt in ("SOLICITUD DEL CAMBIO", "EVALUACIÓN DEL CAMBIO", "RESOLUCIÓN DE LA SOLICITUD", "Probar la bomba", "05/11/2026",
                "Por requerimiento legal o normativo", "Creación del documento"):
        assert txt in hoja, txt
    blanco = c.get("/sgi/solicitudes-cambio/en-blanco").get_data(as_text=True)
    assert "QDV-RG-PG-03_01" in blanco and "Acciones de control" in blanco
    assert "Cambio de bomba" not in blanco and "<input" not in blanco.split('class="sc-sheet"')[1]


def test_sgi_carga_edita_y_queda_historial(app, client, solicitud_id):
    from app.services import solicitud_cambio_service as svc

    c = _login(app, client, "pytest_sc_sgi", is_admin=False, rol="sgi")
    form = {"asunto": "Cambio de bomba dosificadora", "fecha": "20/10/2026", "solicita": "Solicitante A", "prioridad": "Alta",
            "tipos": ["Operativo", "Por reparaciones o contingencias"], "resolucion": "Aceptado", "fecha_resolucion": "22/10/2026",
            "acciones_filas": "3", "ac_actividad_0": "Probar la bomba", "ac_fecha_0": "05/11/2026", "ac_eficacia_0": "Sí",
            "ac_actividad_2": "Capacitar operadores", "ac_responsable_2": "Responsable B"}
    assert c.post(f"/sgi/solicitudes-cambio/{solicitud_id}", data=form).status_code in (302, 303)
    with app.app_context():
        s = svc.get(solicitud_id)
        assert s.resolucion == "Aceptado" and s.fecha_resolucion == date(2026, 10, 22)
        assert s.tipos == "Operativo\nPor reparaciones o contingencias"
        assert [a["actividad"] for a in svc.acciones(s)] == ["Probar la bomba", "Capacitar operadores"]
        assert {x.campo for x in svc.cambios(s)} >= {"resolucion", "fecha_resolucion", "tipos", "acciones_control"}
    hist = c.get(f"/sgi/solicitudes-cambio/{solicitud_id}?historial=1").get_data(as_text=True)
    assert "Historial de cambios" in hist and "22/10/2026" in hist
    assert c.post(f"/sgi/solicitudes-cambio/{solicitud_id}", data={**form, "fecha_evaluacion": "99/99/2026", "solicita": "X"}).status_code in (302, 303)
    with app.app_context():
        assert svc.get(solicitud_id).solicita == "Solicitante A"  # fecha inválida: no guarda nada
    assert c.post("/sgi/solicitudes-cambio/nueva", data={"asunto": "Otra"}).status_code in (302, 303)
    with app.app_context():
        assert [s.numero for s in svc.listar()] == [2, 1]
    c.post(f"/sgi/solicitudes-cambio/{solicitud_id}/baja")  # la baja es del administrador
    with app.app_context():
        assert svc.get(solicitud_id) is not None


def test_admin_da_de_baja(app, client, solicitud_id):
    c = _login(app, client, "pytest_sc_admin2", is_admin=True, rol="operaciones")
    c.post(f"/sgi/solicitudes-cambio/{solicitud_id}/baja")
    assert c.get(f"/sgi/solicitudes-cambio/{solicitud_id}").status_code == 404
    assert "Cambio de bomba" not in c.get("/sgi/solicitudes-cambio/").get_data(as_text=True)


def test_sin_acceso_sgi(app, client, solicitud_id):
    c = _login(app, client, "pytest_sc_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/solicitudes-cambio/", follow_redirects=False).status_code in (302, 303)
    assert c.post(f"/sgi/solicitudes-cambio/{solicitud_id}", data={"asunto": "X"}).status_code in (302, 303)


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        links = proc.registro_modulo_links("solicitud_cambio")
    assert links == {"label": "Solicitudes de cambio", "blank_url": "/sgi/solicitudes-cambio/en-blanco",
                     "filled_url": "/sgi/solicitudes-cambio/"}
