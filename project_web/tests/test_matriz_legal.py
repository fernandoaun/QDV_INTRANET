from __future__ import annotations

import re

from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-ml"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-ml", "csrf_token": tok}).status_code in (302, 303)
    return client


def test_matriz_por_hoja_edicion_e_historial(app, client):
    from app.services import matriz_legal_service as svc

    c = _login(app, client, "pytest_ml_sgi", is_admin=False, rol="sgi")
    html = c.get("/sgi/matriz-legal/").get_data(as_text=True)
    for txt in ("MATRIZ LEGAL Y OTROS REQUISITOS", "QDV-RG-PG-10_01", "21/07/2026", "Nación", "Río Negro", "Otros requisitos",
                "Evidencia objetiva", "Nuevo requisito"):
        assert txt in html, txt
    r = c.post("/sgi/matriz-legal/nuevo", data={"ambito": "rn", "tipo": "legal", "norma": "Ley 3266", "organismo": "Provincia de Río Negro",
                                                "descripcion": "Evaluación de impacto ambiental.", "estado": "cumple"})
    assert r.status_code in (302, 303)
    assert c.post("/sgi/matriz-legal/nuevo", data={"ambito": "nacion"}).status_code == 200  # sin norma ni descripción
    with app.app_context():
        assert svc.listar("nacion") == []
        req = svc.listar("rn")[0]
        assert req.tipo == "Legal" and req.estado == "Cumple" and req.orden == 1
        rid = req.id
    rn = c.get("/sgi/matriz-legal/?hoja=rn").get_data(as_text=True)
    assert "Ley 3266" in rn and "ml-estado-cumple" in rn
    assert "Ley 3266" not in c.get("/sgi/matriz-legal/?hoja=nacion").get_data(as_text=True)
    c.post(f"/sgi/matriz-legal/{rid}", data={"ambito": "rn", "tipo": "Legal", "norma": "Ley 3266", "estado": "No cumple",
                                             "descripcion": "Evaluación de impacto ambiental.", "organismo": "Provincia de Río Negro"})
    with app.app_context():
        req = svc.get(rid)
        assert req.estado == "No cumple" and {x.campo for x in svc.cambios(req)} >= {"alta", "estado"}
        assert svc.ultima_actualizacion()[1] == "pytest_ml_sgi"
    hist = c.get(f"/sgi/matriz-legal/{rid}?historial=1").get_data(as_text=True)
    assert "Historial de cambios" in hist and "No cumple" in hist
    blanco = c.get("/sgi/matriz-legal/en-blanco?hoja=rn").get_data(as_text=True)
    assert "Ley 3266" not in blanco and "Nuevo requisito" not in blanco
    c.post(f"/sgi/matriz-legal/{rid}/baja")  # la baja es del administrador
    with app.app_context():
        assert svc.get(rid) is not None


def test_admin_da_de_baja_y_sin_acceso(app, client):
    from app.extensions import db
    from app.services import matriz_legal_service as svc

    with app.app_context():
        r, _ = svc.crear({"ambito": "otros", "norma": "Contrato cliente A"}, None)
        db.session.commit()
        rid = r.id
    c = _login(app, client, "pytest_ml_admin", is_admin=True, rol="operaciones")
    c.post(f"/sgi/matriz-legal/{rid}/baja")
    assert c.get(f"/sgi/matriz-legal/{rid}").status_code == 404


def test_sin_acceso_sgi(app, client):
    c = _login(app, client, "pytest_ml_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/matriz-legal/", follow_redirects=False).status_code in (302, 303)


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        assert proc.registro_modulo_links("matriz_legal")["blank_url"] == "/sgi/matriz-legal/en-blanco"
