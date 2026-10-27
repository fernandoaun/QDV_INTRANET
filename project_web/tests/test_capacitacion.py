from __future__ import annotations

import json
import re

import pytest
from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-cp"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-cp", "csrf_token": tok}).status_code in (302, 303)
    return client


@pytest.fixture
def capacitacion_id(app):
    from app.extensions import db
    from app.models import EmpleadoPersonal
    from app.services import capacitacion_service as svc

    with app.app_context():
        emp = EmpleadoPersonal(legajo="T-CP-1", apellido="Pérez", nombre="Ana", puesto="Operaria", area="Producción")
        db.session.add(emp)
        db.session.flush()
        c, errs = svc.crear(
            {"tema": "Manejo seguro de hipoclorito", "fecha": "20/10/2026", "lugar": "Planta", "duracion": "2 h",
             "disertantes": "Disertante A", "metodos": {"oral": {"marcado": True, "responsable": "Resp. planta", "plazo": "30 días"}},
             "asistentes": [{"nombre": "perez ana", "sector": "Producción"}, {"nombre": "Externo B", "sector": "Logística"}, {}],
             "eficaz": "si"},
            None,
        )
        assert not errs
        db.session.commit()
        a = svc.asistentes(c)
        assert len(a) == 2 and a[0]["empleado_id"] == emp.id and "empleado_id" not in a[1]
        assert c.eficaz == "SI" and svc.metodos(c) == {"oral": {"marcado": True, "detalle": "", "responsable": "Resp. planta", "plazo": "30 días"}}
        return c.id


def test_listado_hoja_y_en_blanco(app, client, capacitacion_id):
    c = _login(app, client, "pytest_cp_admin", is_admin=True, rol="operaciones")
    html = c.get("/sgi/capacitaciones/").get_data(as_text=True)
    for txt in ("QDV-RG-PG-05_03", "Manejo seguro de hipoclorito", "20/10/2026", "Disertante A", "Nueva capacitación"):
        assert txt in html, txt
    hoja = c.get(f"/sgi/capacitaciones/{capacitacion_id}").get_data(as_text=True)
    for txt in ("REGISTRO DE CAPACITACIÓN", "Evaluación oral", "Resp. planta", "Externo B", "¿Fue eficaz la capacitación realizada?",
                "Confección del registro", "02/06/2026"):
        assert txt in hoja, txt
    blanco = c.get("/sgi/capacitaciones/en-blanco").get_data(as_text=True)
    assert "QDV-RG-PG-05_03" in blanco and "Satisfacción del Cliente" in blanco and "APELLIDO y NOMBRE" in blanco
    assert "Externo B" not in blanco and "<input" not in blanco.split('class="cp-sheet"')[1]
    form = c.get(f"/sgi/capacitaciones/{capacitacion_id}?editar=1").get_data(as_text=True)
    assert 'name="as_nombre_16"' in form and "Pérez, Ana" in form  # 17 renglones y datalist del personal activo


def test_sgi_carga_edita_y_queda_historial(app, client, capacitacion_id):
    from app.services import capacitacion_service as svc

    c = _login(app, client, "pytest_cp_sgi", is_admin=False, rol="sgi")
    form = {"tema": "Manejo seguro de hipoclorito", "fecha": "21/10/2026", "lugar": "Planta", "as_filas": "3", "as_nombre_0": "Pérez, Ana",
            "as_sector_0": "Producción", "as_nombre_2": "Otro C", "m_escrita": "1", "m_escrita_responsable": "SGC",
            "m_otros_detalle": "Observación en planta", "eficaz": "NO", "nuevas_acciones": "SI",
            "nuevas_acciones_detalle": "Repetir en noviembre"}
    assert c.post(f"/sgi/capacitaciones/{capacitacion_id}", data=form).status_code in (302, 303)
    with app.app_context():
        cap = svc.get(capacitacion_id)
        assert [a["nombre"] for a in svc.asistentes(cap)] == ["Pérez, Ana", "Otro C"]
        assert set(svc.metodos(cap)) == {"escrita", "otros"} and not svc.metodos(cap)["otros"]["marcado"]
        assert (cap.eficaz, cap.nuevas_acciones) == ("NO", "SI")
        assert {x.campo for x in svc.cambios(cap)} >= {"fecha", "asistentes", "metodos", "eficaz", "nuevas_acciones"}
    hist = c.get(f"/sgi/capacitaciones/{capacitacion_id}?historial=1").get_data(as_text=True)
    assert "Historial de cambios" in hist and "Otro C · —" in hist
    assert c.post(f"/sgi/capacitaciones/{capacitacion_id}", data={**form, "tema": "", "lugar": "X"}).status_code in (302, 303)
    with app.app_context():
        assert svc.get(capacitacion_id).lugar == "Planta"  # sin tema no guarda nada
    assert c.post("/sgi/capacitaciones/nueva", data={"tema": "Otra"}).status_code in (302, 303)
    with app.app_context():
        assert [x.numero for x in svc.listar()] == [2, 1]
    c.post(f"/sgi/capacitaciones/{capacitacion_id}/baja")  # la baja es del administrador
    with app.app_context():
        assert svc.get(capacitacion_id) is not None


def test_admin_da_de_baja(app, client, capacitacion_id):
    c = _login(app, client, "pytest_cp_admin2", is_admin=True, rol="operaciones")
    c.post(f"/sgi/capacitaciones/{capacitacion_id}/baja")
    assert c.get(f"/sgi/capacitaciones/{capacitacion_id}").status_code == 404


def test_sin_acceso_sgi(app, client, capacitacion_id):
    c = _login(app, client, "pytest_cp_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/capacitaciones/", follow_redirects=False).status_code in (302, 303)
    assert c.post(f"/sgi/capacitaciones/{capacitacion_id}", data={"tema": "X"}).status_code in (302, 303)


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        links = proc.registro_modulo_links("capacitacion")
    assert links == {"label": "Registros de capacitación", "blank_url": "/sgi/capacitaciones/en-blanco",
                     "filled_url": "/sgi/capacitaciones/"}
