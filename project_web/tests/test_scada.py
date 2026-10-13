"""Vista de planta tipo SCADA: mismo acceso que Producción."""
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


def _login(app, client, username, rol):
    import re

    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("x1"), is_admin=False, activo=True, rol=rol))
        db.session.commit()
    page = client.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', page)
    client.post("/login", data={"username": username, "password": "x1", **({"csrf_token": tok.group(1)} if tok else {})})


def test_scada_lo_ven_los_de_produccion(app, client):
    _login(app, client, "op_scada", "operaciones")
    assert client.get("/scada/").status_code == 200
    assert client.get("/scada/estado.json").status_code == 200
    assert "/scada/" in client.get("/dashboard").get_data(as_text=True)


def test_scada_no_lo_ve_quien_no_tiene_produccion(app, client):
    _login(app, client, "sin_prod", "operaciones")
    with client.session_transaction() as sess:
        sess["perms"] = ["sgi"]  # perfil sin ningún permiso de Producción
    assert client.get("/scada/").status_code in (302, 303)
    assert client.get("/scada/estado.json").status_code in (302, 303)
    assert "/scada/" not in client.get("/dashboard").get_data(as_text=True)


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


def test_scada_parar_y_poner_en_marcha(auth_client):
    import re

    page = auth_client.get("/scada/").get_data(as_text=True)
    assert '"salmuera_e2": true' in page
    tok = re.search(r'name="csrf-token" content="([^"]+)"', page)
    h = {"X-CSRFToken": tok.group(1)} if tok else {}
    r = auth_client.post("/produccion/parada-planta", json={"circuit_key": "salmuera_e2", "action": "start", "observaciones": "prueba"}, headers=h)
    assert r.get_json()["ok"]
    e2 = next(e for e in auth_client.get("/scada/estado.json").get_json()["electrolizadores"] if e["id"] == 2)
    assert e2["parada"]["motivo"] == "prueba"
    r = auth_client.post("/produccion/parada-planta", json={"circuit_key": "salmuera_e2", "action": "end"}, headers=h)
    assert r.get_json()["ok"]
    e2 = next(e for e in auth_client.get("/scada/estado.json").get_json()["electrolizadores"] if e["id"] == 2)
    assert e2["parada"] is None


def test_consumo_con_equipo_sugerido_desde_la_planta(auth_client):
    r = auth_client.get("/produccion/stock/consumo?categoria=materia_prima&equipo_id=999")
    assert r.status_code == 200
    assert "PORTAFILTROS" in auth_client.get("/scada/").get_data(as_text=True)
