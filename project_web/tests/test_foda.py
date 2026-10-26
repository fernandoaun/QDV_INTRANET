from __future__ import annotations

import re

from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-fo"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-fo", "csrf_token": tok}).status_code in (302, 303)
    return client


def test_foda_edita_con_historial_y_en_blanco(app, client):
    from app.services import foda_service as svc

    c = _login(app, client, "pytest_fo_sgi", is_admin=False, rol="sgi")
    html = c.get("/sgi/foda/").get_data(as_text=True)
    assert "QDV-RG-PG-09_01" in html and "Fortalezas:" in html and "Amenazas:" in html and "20/05/2026" in html
    r = c.post("/sgi/foda/", data={"fortalezas": "Planta propia\n\n  Personal capacitado ", "amenazas": "Precio de la sal"})
    assert r.status_code in (302, 303)
    with app.app_context():
        f = svc.get()
        assert f.fortalezas == "Planta propia\nPersonal capacitado" and f.amenazas == "Precio de la sal"
        assert {x.campo for x in svc.cambios()} == {"fortalezas", "amenazas"} and svc.ultima_actualizacion() is not None
    c.post("/sgi/foda/", data={"fortalezas": "Planta propia\nPersonal capacitado", "amenazas": "Precio de la sal"})
    with app.app_context():
        assert len(svc.cambios()) == 2  # sin cambios: no suma historial
    html = c.get("/sgi/foda/?historial=1").get_data(as_text=True)
    assert "<li>Personal capacitado</li>" in html and "Historial de cambios" in html
    blanco = c.get("/sgi/foda/en-blanco").get_data(as_text=True)
    assert "Planta propia" not in blanco and "Debilidades:" in blanco


def test_sin_acceso_sgi(app, client):
    c = _login(app, client, "pytest_fo_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/foda/", follow_redirects=False).status_code in (302, 303)
    assert c.post("/sgi/foda/", data={"fortalezas": "X"}).status_code in (302, 303)


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        assert proc.registro_modulo_links("foda") == {"label": "FODA", "blank_url": "/sgi/foda/en-blanco", "filled_url": "/sgi/foda/"}
