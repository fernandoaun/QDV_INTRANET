from __future__ import annotations

import re
from datetime import date

import pytest
from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-ed"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-ed", "csrf_token": tok}).status_code in (302, 303)
    return client


@pytest.fixture
def evaluacion_id(app):
    from app.extensions import db
    from app.models import EmpleadoPersonal
    from app.services import evaluacion_desempeno_service as svc

    with app.app_context():
        emp = EmpleadoPersonal(legajo="T-ED-1", apellido="Pérez", nombre="Ana", puesto="Operaria", area="Producción")
        db.session.add(emp)
        db.session.flush()
        e, errs = svc.crear(
            {"evaluado": "perez ana", "puesto": "Operaria", "periodo": "2026", "evaluador": "Evaluador A", "fecha": "23/10/2026",
             "puntajes": {i: 4 for i in range(1, svc.N_ITEMS + 1)}, "observaciones": "Curso de autoelevador\n\nRefuerzo HSE"},
            None,
        )
        assert not errs
        db.session.commit()
        assert svc.N_ITEMS == 18 and svc.total(e) == 72 and svc.nivel(e) == "Alto"
        assert e.observaciones == "Curso de autoelevador\nRefuerzo HSE"
        return e.id


def test_niveles():
    from app.services import evaluacion_desempeno_service as svc

    class E:
        def __init__(self, n, faltan=0):
            self.puntajes = "{" + ", ".join(f'"{i}": {n}' for i in range(1, 19 - faltan)) + "}"

    assert (svc.total(E(1)), svc.nivel(E(1))) == (18, "Deficiente")
    assert (svc.total(E(2)), svc.nivel(E(2))) == (36, "Bajo")
    assert (svc.total(E(3)), svc.nivel(E(3))) == (54, "Bueno")
    assert (svc.total(E(5)), svc.nivel(E(5))) == (90, "Excelente")
    assert svc.total(E(5, faltan=1)) is None and svc.nivel(E(5, faltan=1)) == ""


def test_listado_hoja_y_en_blanco(app, client, evaluacion_id):
    from app.models import EvaluacionDesempeno

    with app.app_context():
        from app.extensions import db

        assert db.session.get(EvaluacionDesempeno, evaluacion_id).empleado_id is not None  # vinculada al legajo
    c = _login(app, client, "pytest_ed_admin", is_admin=True, rol="operaciones")
    html = c.get("/sgi/evaluaciones-desempeno/").get_data(as_text=True)
    for txt in ("QDV-RG-PG-05_04", "perez ana", "23/10/2026", "72", "Alto", "Nueva evaluación"):
        assert txt in html, txt
    hoja = c.get(f"/sgi/evaluaciones-desempeno/{evaluacion_id}").get_data(as_text=True)
    for txt in ("EVALUACIÓN DE DESEMPEÑO", "ORIENTACIÓN DE RESULTADOS", "TRABAJO EN EQUIPO", "PUNTAJE TOTAL", "72 a 89",
                "Curso de autoelevador", "Objetivos para el próximo período", "Confección del documento", "24/06/2026"):
        assert txt in hoja, txt
    blanco = c.get("/sgi/evaluaciones-desempeno/en-blanco").get_data(as_text=True)
    assert "QDV-RG-PG-05_04" in blanco and "Se identifica fácilmente con los objetivos del equipo" in blanco
    assert "perez ana" not in blanco and "<input" not in blanco.split('class="ed-sheet"')[1]
    form = c.get(f"/sgi/evaluaciones-desempeno/{evaluacion_id}?editar=1").get_data(as_text=True)
    assert 'name="p_18"' in form and "Pérez, Ana" in form  # datalist del personal activo


def test_sgi_carga_edita_y_queda_historial(app, client, evaluacion_id):
    from app.services import evaluacion_desempeno_service as svc

    c = _login(app, client, "pytest_ed_sgi", is_admin=False, rol="sgi")
    form = {"evaluado": "Pérez, Ana", "fecha": "23/10/2026", "periodo": "2026", "obs_filas": "3", "obs_0": "Curso de autoelevador",
            "obj_filas": "2", "obj_1": "Llegar a nivel Excelente", "comentarios_evaluador": "Muy buen año.",
            **{f"p_{i}": "5" for i in range(1, 19)}}
    assert c.post(f"/sgi/evaluaciones-desempeno/{evaluacion_id}", data=form).status_code in (302, 303)
    with app.app_context():
        e = svc.get(evaluacion_id)
        assert svc.total(e) == 90 and svc.nivel(e) == "Excelente"
        assert e.observaciones == "Curso de autoelevador" and e.objetivos == "Llegar a nivel Excelente"
        assert {x.campo for x in svc.cambios(e)} >= {"puntajes", "observaciones", "objetivos", "comentarios_evaluador"}
    hist = c.get(f"/sgi/evaluaciones-desempeno/{evaluacion_id}?historial=1").get_data(as_text=True)
    assert "Historial de cambios" in hist and "total 90" in hist
    assert c.post(f"/sgi/evaluaciones-desempeno/{evaluacion_id}", data={**form, "p_3": "7", "periodo": "X"}).status_code in (302, 303)
    with app.app_context():
        assert svc.get(evaluacion_id).periodo == "2026"  # puntaje fuera de escala: no guarda nada
    assert c.post("/sgi/evaluaciones-desempeno/nueva", data={"evaluado": "Otro"}).status_code in (302, 303)
    with app.app_context():
        assert [e.numero for e in svc.listar()] == [2, 1]
    c.post(f"/sgi/evaluaciones-desempeno/{evaluacion_id}/baja")  # la baja es del administrador
    with app.app_context():
        assert svc.get(evaluacion_id) is not None


def test_admin_da_de_baja(app, client, evaluacion_id):
    c = _login(app, client, "pytest_ed_admin2", is_admin=True, rol="operaciones")
    c.post(f"/sgi/evaluaciones-desempeno/{evaluacion_id}/baja")
    assert c.get(f"/sgi/evaluaciones-desempeno/{evaluacion_id}").status_code == 404


def test_sin_acceso_sgi(app, client, evaluacion_id):
    c = _login(app, client, "pytest_ed_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/evaluaciones-desempeno/", follow_redirects=False).status_code in (302, 303)
    assert c.post(f"/sgi/evaluaciones-desempeno/{evaluacion_id}", data={"evaluado": "X"}).status_code in (302, 303)


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        links = proc.registro_modulo_links("evaluacion_desempeno")
    assert links == {"label": "Evaluaciones de desempeño", "blank_url": "/sgi/evaluaciones-desempeno/en-blanco",
                     "filled_url": "/sgi/evaluaciones-desempeno/"}
