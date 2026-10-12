"""Vista de planta tipo SCADA: solo administrador por ahora."""
from __future__ import annotations


def test_scada_admin_ve_la_planta_y_el_estado(auth_client):
    r = auth_client.get("/scada/")
    assert r.status_code == 200
    assert "Planta en vivo" in r.get_data(as_text=True)
    r = auth_client.get("/scada/estado.json")
    assert r.status_code == 200
    data = r.get_json()
    for clave in ("turno", "cronometros", "electrolizadores", "salmuera", "agua", "materias_primas", "hipoclorito"):
        assert clave in data
        assert not (isinstance(data[clave], dict) and data[clave].get("error")), clave


def test_scada_no_admin_no_entra(app, client):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username="op_scada", password_hash=generate_password_hash("x1"), is_admin=False, activo=True, rol="operaciones"))
        db.session.commit()
    import re

    page = client.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', page)
    client.post("/login", data={"username": "op_scada", "password": "x1", **({"csrf_token": tok.group(1)} if tok else {})})
    assert client.get("/scada/").status_code in (302, 303)
    assert client.get("/scada/estado.json").status_code in (302, 303)


def test_scada_va_entre_panel_y_produccion(auth_client):
    html = auth_client.get("/dashboard").get_data(as_text=True)
    i_panel = html.index('title="Panel"><i class="bi bi-speedometer2"')
    i_scada = html.index("/scada/")
    i_prod = html.index('title="PRODUCCIÓN')
    assert i_panel < i_scada < i_prod


def test_paginas_de_carga_se_pueden_embeber_en_la_planta(auth_client):
    r = auth_client.get("/scada/")
    assert "data-form" in r.get_data(as_text=True)
    page = auth_client.get("/dashboard")
    assert "app-embedded" in page.get_data(as_text=True)
