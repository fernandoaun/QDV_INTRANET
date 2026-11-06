from __future__ import annotations

import re

from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-ck"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-ck", "csrf_token": tok}).status_code in (302, 303)
    return client


def _equipo(app) -> int:
    from app.extensions import db
    from app.models import Equipo

    with app.app_context():
        e = Equipo(nombre_equipo="Compresor de aire", descripcion="", area_sector="Sala de compresores",
                   created_at_iso="2026-11-06T10:00:00")
        db.session.add(e)
        db.session.commit()
        return e.id


def test_checklist_se_arma_se_completa_y_se_firma(app, client):
    from app.services import mant_checklist_service as ck

    eid = _equipo(app)
    c = _login(app, client, "pytest_ck_admin", is_admin=True, rol="operaciones", nombre_completo="Aun, Silvio Fernando")
    c.post(f"/mantenimiento/equipos/{eid}/checklist", data={
        "codigo": "QDV-RG-PO-01_07", "titulo": "Check list de compresor de aire",
        "items": "Toma de aire\nPresostato\n\nVálvula de purga\n"})
    with app.app_context():
        assert ck.items(ck.get_de_equipo(eid)) == ["Toma de aire", "Presostato", "Válvula de purga"]
    hoja = c.get(f"/mantenimiento/equipos/{eid}/checklist/nuevo").get_data(as_text=True)
    assert "QDV-RG-PO-01_07" in hoja and "CHECK LIST DE COMPRESOR DE AIRE" in hoja and "Sala de compresores" in hoja
    base = {"fecha": "06/11/2026", "area": "Sala de compresores", "actividad": "Inspección mensual",
            "item_0": "Buen estado", "item_1": "Mal estado", "item_2": "Buen estado"}
    r = c.post(f"/mantenimiento/equipos/{eid}/checklist/nuevo", data={**base, "item_2": ""})
    assert "Marcá «Buen estado» o «Mal estado» en: Válvula de purga." in r.get_data(as_text=True)
    r = c.post(f"/mantenimiento/equipos/{eid}/checklist/nuevo", data=base)
    assert "describí en observaciones" in r.get_data(as_text=True)
    r = c.post(f"/mantenimiento/equipos/{eid}/checklist/nuevo", data={**base, "observaciones": "Presostato no corta."})
    assert r.status_code in (302, 303)
    rid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    with app.app_context():
        reg = ck.get_registro(rid)
        assert reg.numero == 1 and ck.mal_estado(reg) == ["Presostato"] and reg.inspector_nombre == "Aun, Silvio Fernando"
        assert reg.planta_firma_at is None
    hoja = c.get(f"/mantenimiento/checklists/{rid}").get_data(as_text=True)
    assert "Firmado en el sistema por Aun, Silvio Fernando" in hoja and "Pendiente de firma" in hoja
    c.post(f"/mantenimiento/checklists/{rid}")
    with app.app_context():
        assert ck.get_registro(rid).planta_firma_at is not None
    assert "Pendiente de firma" not in c.get(f"/mantenimiento/checklists/{rid}").get_data(as_text=True)
    assert "Presostato en mal estado" in c.get(f"/mantenimiento/equipos/{eid}").get_data(as_text=True)
    assert "QDV-RG-PO-01_07 N° 1" in c.get("/mantenimiento/checklists").get_data(as_text=True)


def test_registro_sgi_checklists(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        links = proc.registro_modulo_links("mant_checklists")
    assert links["filled_url"] == "/mantenimiento/checklists"
