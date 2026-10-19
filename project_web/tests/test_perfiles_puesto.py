from __future__ import annotations

import re

import pytest
from werkzeug.security import generate_password_hash


def _doc(puesto="Jefe test", supervisor="Gerencia test") -> bytes:
    """Perfil con la misma estructura que la plantilla Word del registro (datos ficticios).

    En un .doc de Word 97 el texto va en cp1252: \\x07 cierra cada celda y \\r separa renglones.
    """
    celdas = [
        "INFORMACIÓN PRINCIPAL", "",
        "Denominación del cargo:", puesto,
        "Proceso:", "Proceso test",
        "Supervisor Inmediato / Directo:", supervisor,
        "Supervisa a:", "",
        "Interactúa principalmente con:", "Sector A; Sector B.", "",
        "\rDESCRIPCIÓN DEL CARGO", "",
        "Principales Tareas y Responsabilidades:", "", "Tarea uno.\rTarea dos.\r", "",
        "\rCOMPETENCIAS", "",
        "Competencias Cognitivas:", "",
        "Educación requerida: ", "Secundario completo.",
        "Formación requerida:", "Curso A.\rCurso B.",
        "Idiomas y otros", "Español.",
        "Competencias funcionales:", "",
        "Experiencia Previa: ", "\r2 años.\r",
        "Competencias Aptitudinales – Habilidades:", "\rOrden.\rLiderazgo.\r",
        "Posee Autoridad para:", "\rDecidir A.\r",
        "Rendición de Cuentas:", "\rResultado A.\rResultado B.",
        "\rFecha de Actualización: 01/09/2026\rAprobado por: Gerencia test\r\r",
        "Revisión", "Control de Cambios", "Fecha",
    ]
    return ("basura binaria" + "\x07".join(celdas) + "\x07").encode("cp1252")


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-perfiles"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-perfiles", "csrf_token": tok}).status_code in (302, 303)
    return client


def test_leer_doc_de_la_plantilla(app):
    from datetime import date

    from app.services import perfiles_puesto_service as svc

    data, err = svc.leer_doc(_doc())
    assert err is None
    assert data["puesto"] == "Jefe test" and data["supervisor"] == "Gerencia test" and data["proceso"] == "Proceso test"
    assert data["supervisa_a"] == []  # vacío en la plantilla: no se come el rótulo siguiente
    assert data["interactua_con"] == ["Sector A; Sector B."]
    assert data["tareas"] == ["Tarea uno.", "Tarea dos."]
    assert data["formacion"] == ["Curso A.", "Curso B."] and data["habilidades"] == ["Orden.", "Liderazgo."]
    assert data["rendicion_cuentas"] == ["Resultado A.", "Resultado B."]
    assert data["fecha_actualizacion"] == date(2026, 9, 1) and data["aprobado_por"] == "Gerencia test"
    assert svc.leer_doc(b"no es un perfil")[1]


@pytest.fixture
def perfil_id(app):
    from app.extensions import db
    from app.services import perfiles_puesto_service as svc

    with app.app_context():
        data, _ = svc.leer_doc(_doc())
        p, errs = svc.crear(data, None, fecha_actualizacion=data["fecha_actualizacion"])
        assert not errs
        db.session.commit()
        return p.id


def test_listado_perfil_y_en_blanco(app, client, perfil_id):
    c = _login(app, client, "pytest_perfiles_admin", is_admin=True, rol="operaciones")
    listado = c.get("/sgi/perfiles-puesto/").get_data(as_text=True)
    assert "Jefe test" in listado and "Gerencia test" in listado and "Nuevo perfil" in listado

    html = c.get(f"/sgi/perfiles-puesto/{perfil_id}").get_data(as_text=True)
    for txt in ("PERFIL DE PUESTO", "QDV-RG-PG-05_01", "INFORMACIÓN PRINCIPAL", "DESCRIPCIÓN DEL CARGO", "COMPETENCIAS",
                "Jefe test", "Tarea dos.", "Curso B.", "Liderazgo.", "01/09/2026"):
        assert txt in html, txt

    blanco = c.get("/sgi/perfiles-puesto/en-blanco").get_data(as_text=True)
    assert "PERFIL DE PUESTO" in blanco and "QDV-RG-PG-05_01" in blanco and "Rendición de cuentas" in blanco
    assert "Jefe test" not in blanco and "Tarea dos." not in blanco and "Editar" not in blanco


def test_sgi_edita_campos_y_queda_historial(app, client, perfil_id):
    c = _login(app, client, "pytest_perfiles_sgi", is_admin=False, rol="sgi")
    assert 'name="tareas"' in c.get(f"/sgi/perfiles-puesto/{perfil_id}?editar=1").get_data(as_text=True)
    r = c.post(
        f"/sgi/perfiles-puesto/{perfil_id}",
        data={"puesto": "Jefe test", "proceso": "Proceso test", "supervisor": "Gerencia nueva",
              "tareas": "Tarea uno.\n\nTarea dos.\nTarea tres.", "habilidades": "Orden.", "aprobado_por": "Gerencia test"},
    )
    assert r.status_code in (302, 303)
    from app.services import perfiles_puesto_service as svc

    with app.app_context():
        p = svc.get(perfil_id)
        assert p.supervisor == "Gerencia nueva" and svc.items(p.tareas) == ["Tarea uno.", "Tarea dos.", "Tarea tres."]
        assert {x.campo for x in svc.cambios(p)} >= {"supervisor", "tareas", "habilidades"}
    hist = c.get(f"/sgi/perfiles-puesto/{perfil_id}?historial=1").get_data(as_text=True)
    assert "Historial de cambios" in hist and "Gerencia nueva" in hist
    # Alta y baja son del administrador.
    c.post(f"/sgi/perfiles-puesto/{perfil_id}/baja")
    with app.app_context():
        assert svc.get(perfil_id) is not None
    assert c.get("/sgi/perfiles-puesto/nuevo", follow_redirects=False).status_code in (302, 303)


def test_admin_crea_y_da_de_baja(app, client):
    c = _login(app, client, "pytest_perfiles_admin2", is_admin=True, rol="operaciones")
    r = c.post("/sgi/perfiles-puesto/nuevo", data={"puesto": "Puesto test", "tareas": "Hacer."})
    assert r.status_code in (302, 303)
    pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    assert c.post("/sgi/perfiles-puesto/nuevo", data={"puesto": ""}).status_code == 200
    c.post(f"/sgi/perfiles-puesto/{pid}/baja")
    assert c.get(f"/sgi/perfiles-puesto/{pid}").status_code == 404
    assert ">Puesto test</a>" not in c.get("/sgi/perfiles-puesto/").get_data(as_text=True)


def test_sin_acceso_sgi(app, client, perfil_id):
    c = _login(app, client, "pytest_perfiles_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/perfiles-puesto/", follow_redirects=False).status_code in (302, 303)
    assert c.post(f"/sgi/perfiles-puesto/{perfil_id}", data={"puesto": "X"}).status_code in (302, 303)


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        links = proc.registro_modulo_links("perfiles_puesto")
    assert links == {"label": "Perfiles de puesto", "blank_url": "/sgi/perfiles-puesto/en-blanco", "filled_url": "/sgi/perfiles-puesto/"}
