from __future__ import annotations

import re
from datetime import date

import pytest
from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-mr"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-mr", "csrf_token": tok}).status_code in (302, 303)
    return client


@pytest.fixture
def minuta_id(app):
    from app.extensions import db
    from app.services import minuta_reunion_service as svc

    with app.app_context():
        m, errs = svc.crear(
            {"motivo": "Revisión por la dirección", "fecha": "21/10/2026", "horario": "10:00 a 11:30", "lugar": "Oficina de planta",
             "participantes": [{"participante": "Participante A", "sector": "SGC", "asistencia": "presente"},
                               {"participante": "Participante B", "sector": "Producción", "asistencia": "Ausente"}],
             "acciones": [{"accion": "Actualizar el PG-04", "responsable": "Participante A", "fecha": "2026-11-15"}]},
            None,
        )
        assert not errs
        db.session.commit()
        assert m.numero == 1 and svc.presentes(m) == 1
        assert svc.filas(m, "acciones") == [{"accion": "Actualizar el PG-04", "responsable": "Participante A", "fecha": "15/11/2026"}]
        return m.id


def test_listado_hoja_y_en_blanco(app, client, minuta_id):
    c = _login(app, client, "pytest_mr_admin", is_admin=True, rol="operaciones")
    html = c.get("/sgi/minutas-reunion/").get_data(as_text=True)
    for txt in ("QDV-RG-PG-04_01", "Revisión por la dirección", "21/10/2026", "Nueva minuta"):
        assert txt in html, txt
    hoja = c.get(f"/sgi/minutas-reunion/{minuta_id}").get_data(as_text=True)
    for txt in ("MINUTA DE REUNIÓN", "PARTICIPANTE", "DESARROLLO", "ACCIONES / CONCLUSIONES", "Participante B", "Ausente",
                "15/11/2026", "Confección del documento"):
        assert txt in hoja, txt
    blanco = c.get("/sgi/minutas-reunion/en-blanco").get_data(as_text=True)
    assert "QDV-RG-PG-04_01" in blanco and "SECTOR / EMPRESA" in blanco
    assert "Revisión por la dirección" not in blanco and "<input" not in blanco.split('class="mr-sheet"')[1]


def test_sgi_carga_edita_y_queda_historial(app, client, minuta_id):
    from app.services import minuta_reunion_service as svc

    c = _login(app, client, "pytest_mr_sgi", is_admin=False, rol="sgi")
    form = {"motivo": "Revisión por la dirección", "fecha": "21/10/2026", "lugar": "Oficina de planta", "desarrollo": "Se revisaron los objetivos.",
            "participantes_filas": "3", "participantes_participante_0": "Participante A", "participantes_asistencia_0": "Presente",
            "participantes_participante_2": "Participante C", "participantes_sector_2": "Externo", "participantes_asistencia_2": "Presente",
            "acciones_filas": "2", "acciones_accion_1": "Comprar repuestos", "acciones_fecha_1": "30/11/2026"}
    assert c.post(f"/sgi/minutas-reunion/{minuta_id}", data=form).status_code in (302, 303)
    with app.app_context():
        m = svc.get(minuta_id)
        assert m.desarrollo == "Se revisaron los objetivos." and svc.presentes(m) == 2
        assert [p["participante"] for p in svc.filas(m, "participantes")] == ["Participante A", "Participante C"]
        assert svc.filas(m, "acciones") == [{"accion": "Comprar repuestos", "responsable": "", "fecha": "30/11/2026"}]
        assert {x.campo for x in svc.cambios(m)} >= {"desarrollo", "participantes", "acciones"}
    hist = c.get(f"/sgi/minutas-reunion/{minuta_id}?historial=1").get_data(as_text=True)
    assert "Historial de cambios" in hist and "30/11/2026" in hist
    assert c.post(f"/sgi/minutas-reunion/{minuta_id}", data={**form, "fecha": "31/02/2026", "lugar": "X"}).status_code in (302, 303)
    with app.app_context():
        m = svc.get(minuta_id)
        assert m.lugar == "Oficina de planta" and m.fecha == date(2026, 10, 21)  # fecha inválida: no guarda nada
    assert c.post("/sgi/minutas-reunion/nueva", data={"motivo": "Otra"}).status_code in (302, 303)
    with app.app_context():
        assert [m.numero for m in svc.listar()] == [2, 1]
    c.post(f"/sgi/minutas-reunion/{minuta_id}/baja")  # la baja es del administrador
    with app.app_context():
        assert svc.get(minuta_id) is not None


def test_admin_da_de_baja(app, client, minuta_id):
    c = _login(app, client, "pytest_mr_admin2", is_admin=True, rol="operaciones")
    c.post(f"/sgi/minutas-reunion/{minuta_id}/baja")
    assert c.get(f"/sgi/minutas-reunion/{minuta_id}").status_code == 404
    assert "Revisión por la dirección" not in c.get("/sgi/minutas-reunion/").get_data(as_text=True)


def test_sin_acceso_sgi(app, client, minuta_id):
    c = _login(app, client, "pytest_mr_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/minutas-reunion/", follow_redirects=False).status_code in (302, 303)
    assert c.post(f"/sgi/minutas-reunion/{minuta_id}", data={"motivo": "X"}).status_code in (302, 303)


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        links = proc.registro_modulo_links("minuta_reunion")
    assert links == {"label": "Minutas de reunión", "blank_url": "/sgi/minutas-reunion/en-blanco",
                     "filled_url": "/sgi/minutas-reunion/"}
