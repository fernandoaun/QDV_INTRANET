from __future__ import annotations

import re

from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-rd"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-rd", "csrf_token": tok}).status_code in (302, 303)
    return client


def _form(svc, **extra):
    f = {"fecha": "24/11/2026", "participantes_filas": "2",
         "participantes_participante_0": "Pérez, Ana", "participantes_cargo_0": "Responsable de Planta",
         "participantes_participante_1": "Gómez, Luis", "participantes_cargo_1": "Gerencia General",
         "acciones_filas": "1", "acciones_accion_0": "Revisar objetivos 2027", "acciones_responsable_0": "Gómez, Luis",
         "acciones_fecha_0": "15/12/2026"}
    f.update({f"tema_{k}": f"Tratado: {k}" for k in svc.CLAVES_TEMAS})
    f.update(extra)
    return f


def test_hoja_en_blanco_y_registro(app, client):
    from app.services import sgi_procedimiento_service as proc

    c = _login(app, client, "pytest_rd_admin", is_admin=True, rol="operaciones")
    blanco = c.get("/sgi/revision-direccion/en-blanco").get_data(as_text=True)
    for txt in ("QDV-RG-PG-07_01", "MINUTA DE REVISIÓN POR LA DIRECCIÓN", "Estado de acciones de revisiones por la dirección previas",
                "El desempeño SYSO de la organización", "PARTICIPANTES DE LA REUNIÓN", "CARGO", "Confección del formulario", "24/11/2026"):
        assert txt in blanco, txt
    hoja = blanco.split('class="rd-sheet"')[1].split("</form>")[0]
    assert "<input" not in hoja and "<textarea" not in hoja
    with app.app_context():
        assert proc.registro_modulo_links("revision_direccion") == {
            "label": "Minutas de revisión por la dirección", "blank_url": "/sgi/revision-direccion/en-blanco",
            "filled_url": "/sgi/revision-direccion/"}


def test_carga_obligatoria_plan_firmas_y_anulacion(app, client, monkeypatch):
    from app.extensions import db
    from app.models import User
    from app.services import accion_link_service as accion_svc
    from app.services import avisos_pendientes_service as avisos
    from app.services import plan_accion_service as plan
    from app.services import revision_direccion_service as svc

    monkeypatch.setattr(svc, "avisar_firmas", lambda *a, **k: 0)
    c = _login(app, client, "pytest_rd_sgi", is_admin=False, rol="sgi", nombre_completo="Pérez, Ana")
    with app.app_context():
        db.session.add(User(username="pytest_rd_otro", password_hash="x", activo=True, rol="sgi", nombre_completo="Gómez, Luis"))
        db.session.commit()
    html = c.post("/sgi/revision-direccion/nueva", data=_form(svc, tema_syso="")).get_data(as_text=True)
    assert "Completá todos los temas" in html and "Tratado: recursos" in html  # no se pierde lo escrito
    with app.app_context():
        assert svc.listar() == []
    r = c.post("/sgi/revision-direccion/nueva", data=_form(svc))
    rid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    with app.app_context():
        rev = svc.get(rid)
        assert rev.numero == 1 and svc.temas(rev)["otros"] == "Tratado: otros"
        assert [a.accion for a in plan.listar()] == ["Revisar objetivos 2027"]
        assert "QDV-RG-PG-07_01" in plan.listar()[0].requisito
    hoja = c.get(f"/sgi/revision-direccion/{rid}").get_data(as_text=True)
    assert "Firmas: 0 de 2" in hoja and "Firmar</button>" in hoja and "Plan de acción N° 1" in hoja
    c.post(f"/sgi/revision-direccion/{rid}/firmar")
    with app.test_request_context():
        otro = db.session.query(User).filter_by(username="pytest_rd_otro").one()
        items = [p for p in avisos.pendientes(otro) if p["tipo"] == accion_svc.REVDIR_FIRMAR]
        assert len(items) == 1 and "Tratado: syso" in items[0]["texto"]
        avisos.ejecutar(otro, {"pendiente": items[0]["pendiente"], "accion": "firmar"})
        assert svc.firmas(svc.get(rid)) == (2, 2)
        token = accion_svc.crear_token(app, accion_svc.REVDIR_FIRMAR, rid, user_id=otro.id)
    assert "No tenés esta minuta pendiente de firma" in client.get(f"/accion/{token}").get_data(as_text=True)
    c.post(f"/sgi/revision-direccion/{rid}", data=_form(svc))
    with app.app_context():
        assert svc.firmas(svc.get(rid)) == (2, 2) and len(plan.listar()) == 1
    c.post(f"/sgi/revision-direccion/{rid}", data=_form(svc, tema_mejora="Otra cosa"))
    with app.app_context():
        rev = svc.get(rid)
        assert svc.firmas(rev) == (0, 2) and any(x.campo == "firmas" for x in svc.cambios(rev))


def test_sin_acceso_sgi(app, client):
    c = _login(app, client, "pytest_rd_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/revision-direccion/", follow_redirects=False).status_code in (302, 303)
