from __future__ import annotations

import re

from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-mp"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-mp", "csrf_token": tok}).status_code in (302, 303)
    return client


def test_mapa_enlaza_las_fichas(app, client):
    from app.extensions import db
    from app.models import FichaProceso

    with app.app_context():
        for nombre in ("GERENCIA", "SGC", "Producción", "Control de calidad", "Compras y Proveedores"):
            db.session.add(FichaProceso(proceso=nombre))
        db.session.commit()
        ids = {f.proceso: f.id for f in db.session.query(FichaProceso)}
    c = _login(app, client, "pytest_mp_sgi", is_admin=False, rol="sgi")
    html = c.get("/sgi/mapa-procesos/").get_data(as_text=True)
    for txt in ("MAPA DE PROCESOS", "QDV-RG-PG-09_02", "12/05/2026", "20/05/2026", "PROCESOS ESTRATÉGICOS", "Electrólisis",
                "Declorinación secundaria", "Metabisulfito de sodio", "Agua lavandina"):
        assert txt in html, txt
    for nombre in ("GERENCIA", "SGC", "Producción", "Control de calidad", "Compras y Proveedores"):
        assert f'/sgi/fichas-proceso/{ids[nombre]}"' in html, nombre  # sin tildes ni mayúsculas
    assert "Mantenimiento" in html  # sin ficha: se muestra igual, sin enlace


def test_sin_acceso_sgi(app, client):
    c = _login(app, client, "pytest_mp_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/mapa-procesos/", follow_redirects=False).status_code in (302, 303)
