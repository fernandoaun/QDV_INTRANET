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
             "desarrollo": "Se revisan los indicadores.",
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
                "15/11/2026", "Confección del documento", "FIRMA", "No firma (ausente)", "Sin usuario del sistema"):
        assert txt in hoja, txt
    blanco = c.get("/sgi/minutas-reunion/en-blanco").get_data(as_text=True)
    assert "QDV-RG-PG-04_01" in blanco and "SECTOR / EMPRESA" in blanco
    assert "Revisión por la dirección" not in blanco and "<input" not in blanco.split('class="mr-sheet"')[1]


def test_sgi_carga_edita_y_queda_historial(app, client, minuta_id):
    from app.services import minuta_reunion_service as svc

    c = _login(app, client, "pytest_mr_sgi", is_admin=False, rol="sgi")
    form = {"motivo": "Revisión por la dirección", "fecha": "21/10/2026", "horario": "10:00", "lugar": "Oficina de planta",
            "desarrollo": "Se revisaron los objetivos.",
            "participantes_filas": "3", "participantes_participante_0": "Participante A", "participantes_sector_0": "SGC",
            "participantes_asistencia_0": "Presente",
            "participantes_participante_2": "Participante C", "participantes_sector_2": "Externo", "participantes_asistencia_2": "Presente",
            "acciones_filas": "2", "acciones_accion_1": "Comprar repuestos", "acciones_responsable_1": "Participante C",
            "acciones_fecha_1": "30/11/2026"}
    assert c.post(f"/sgi/minutas-reunion/{minuta_id}", data=form).status_code in (302, 303)
    with app.app_context():
        m = svc.get(minuta_id)
        assert m.desarrollo == "Se revisaron los objetivos." and svc.presentes(m) == 2
        assert [p["participante"] for p in svc.filas(m, "participantes")] == ["Participante A", "Participante C"]
        assert [(a["accion"], a["responsable"], a["fecha"]) for a in svc.filas(m, "acciones")] == [
            ("Comprar repuestos", "Participante C", "30/11/2026")]
        assert {x.campo for x in svc.cambios(m)} >= {"desarrollo", "participantes", "acciones"}
    hist = c.get(f"/sgi/minutas-reunion/{minuta_id}?historial=1").get_data(as_text=True)
    assert "Historial de cambios" in hist and "30/11/2026" in hist
    assert c.post(f"/sgi/minutas-reunion/{minuta_id}", data={**form, "fecha": "31/02/2026", "lugar": "X"}).status_code in (302, 303)
    with app.app_context():
        m = svc.get(minuta_id)
        assert m.lugar == "Oficina de planta" and m.fecha == date(2026, 10, 21)  # fecha inválida: no guarda nada
    assert c.post(f"/sgi/minutas-reunion/{minuta_id}", data={**form, "horario": ""}).status_code in (302, 303)
    assert c.post(f"/sgi/minutas-reunion/{minuta_id}", data={**form, "participantes_sector_2": ""}).status_code in (302, 303)
    assert c.post(f"/sgi/minutas-reunion/{minuta_id}", data={**form, "acciones_responsable_1": ""}).status_code in (302, 303)
    with app.app_context():
        assert svc.get(minuta_id).horario == "10:00"  # campos vacíos: no guarda
    assert c.post("/sgi/minutas-reunion/nueva", data={"motivo": "Otra"}).status_code in (200, 302, 303)
    with app.app_context():
        assert [m.numero for m in svc.listar()] == [1]
    assert c.post("/sgi/minutas-reunion/nueva", data={**form, "motivo": "Otra"}).status_code in (302, 303)
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


def test_acciones_con_responsable_pasan_al_plan(app, client, minuta_id):
    from app.services import minuta_reunion_service as svc
    from app.services import plan_accion_service as plan

    c = _login(app, client, "pytest_mr_plan", is_admin=False, rol="sgi")
    with app.app_context():
        m = svc.get(minuta_id)
        assert svc.sincronizar_plan(m, None) == 1  # la fila del fixture tiene responsable
        from app.extensions import db

        db.session.commit()
        pa_id = svc.filas(m, "acciones")[0]["plan_accion_id"]
        pa = plan.get(pa_id)
        assert pa.origen == "Minuta de reunión" and pa.requisito == "QDV-RG-PG-04_01 Minuta N° 1"
        assert pa.fecha_deteccion == date(2026, 10, 21) and pa.fecha_cumplimiento == date(2026, 11, 15)
        assert pa.estado == "En curso" and pa.responsable == "Participante A"
    form = {"motivo": "Revisión por la dirección", "fecha": "21/10/2026", "horario": "10:00", "lugar": "Oficina",
            "desarrollo": "Se revisan las acciones.", "participantes_filas": "1", "participantes_participante_0": "Participante A",
            "participantes_sector_0": "SGC", "participantes_asistencia_0": "Presente", "acciones_filas": "3",
            "acciones_accion_0": "Actualizar el PG-04 y difundirlo", "acciones_responsable_0": "Participante B",
            "acciones_fecha_0": "20/11/2026", "acciones_plan_0": str(pa_id),
            "acciones_accion_2": "Comprar repuestos", "acciones_responsable_2": "Participante C", "acciones_fecha_2": "30/11/2026"}
    r = c.post(f"/sgi/minutas-reunion/{minuta_id}", data=form)
    assert r.status_code in (302, 303)
    with app.app_context():
        acciones = plan.listar()
        assert [a.accion for a in acciones] == ["Actualizar el PG-04 y difundirlo", "Comprar repuestos"]
        assert acciones[0].id == pa_id and acciones[0].responsable == "Participante B"
        assert acciones[0].fecha_cumplimiento == date(2026, 11, 20)
        assert {x.campo for x in plan.cambios(acciones[0])} >= {"accion", "responsable", "fecha_cumplimiento"}
    c.post(f"/sgi/minutas-reunion/{minuta_id}", data=form)  # volver a guardar no duplica
    with app.app_context():
        assert len(plan.listar()) == 2
    hoja = c.get(f"/sgi/minutas-reunion/{minuta_id}").get_data(as_text=True)
    assert "Plan de acción N° 1" in hoja and "Plan de acción N° 2" in hoja


def test_firma_por_sistema_y_se_anula_al_modificar(app, client, monkeypatch):
    from app.extensions import db
    from app.models import User
    from app.services import accion_link_service as accion_svc
    from app.services import avisos_pendientes_service as avisos
    from app.services import minuta_reunion_service as svc

    monkeypatch.setattr(svc, "avisar_firmas", lambda *a, **k: 0)
    c = _login(app, client, "pytest_mr_firma", is_admin=False, rol="sgi", nombre_completo="Pérez, Ana")
    with app.app_context():
        db.session.add(User(username="pytest_mr_otro", password_hash="x", activo=True, rol="sgi", nombre_completo="Gómez, Luis"))
        db.session.commit()
    form = {"motivo": "Aprobación", "fecha": "05/11/2026", "horario": "09:00 a 10:00", "lugar": "Oficina", "desarrollo": "Se aprueba.",
            "participantes_filas": "3",
            "participantes_participante_0": "Ana Perez", "participantes_sector_0": "SGC", "participantes_asistencia_0": "Presente",
            "participantes_participante_1": "Gómez, Luis", "participantes_sector_1": "Gerencia", "participantes_asistencia_1": "Presente",
            "participantes_participante_2": "Auditor externo", "participantes_sector_2": "Certificadora", "participantes_asistencia_2": "Presente",
            "acciones_filas": "1", "acciones_accion_0": "Difundir", "acciones_responsable_0": "Pérez, Ana", "acciones_fecha_0": "06/11/2026"}
    r = c.post("/sgi/minutas-reunion/nueva", data=form)
    mid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    hoja = c.get(f"/sgi/minutas-reunion/{mid}").get_data(as_text=True)
    assert "Pendiente de firma" in hoja and "Sin usuario del sistema" in hoja and "Firmas: 0 de 2" in hoja and "Firmar</button>" in hoja
    c.post(f"/sgi/minutas-reunion/{mid}/firmar")
    with app.test_request_context():
        m = svc.get(mid)
        assert svc.firmas(m) == (1, 2)
        otro = db.session.query(User).filter_by(username="pytest_mr_otro").one()
        items = [p for p in avisos.pendientes(otro) if p["tipo"] == accion_svc.MINUTA_FIRMAR]
        assert len(items) == 1 and "Se aprueba." in items[0]["texto"]
        res = avisos.ejecutar(otro, {"pendiente": items[0]["pendiente"], "accion": "firmar"})
        assert "firmaste" in res["message"]
        m = svc.get(mid)
        assert svc.firmas(m) == (2, 2)
        assert "Firmado en el sistema (WhatsApp)" in svc.firma_texto(svc.filas(m, "participantes")[1])
    hoja = c.get(f"/sgi/minutas-reunion/{mid}").get_data(as_text=True)
    assert "Firmado en el sistema (sistema)" in hoja and "Firmas: 2 de 2" in hoja
    c.post(f"/sgi/minutas-reunion/{mid}", data=form)  # guardar sin cambios conserva las firmas
    with app.app_context():
        assert svc.firmas(svc.get(mid)) == (2, 2)
    c.post(f"/sgi/minutas-reunion/{mid}", data={**form, "desarrollo": "Se aprueba con cambios."})
    with app.app_context():
        m = svc.get(mid)
        assert svc.firmas(m) == (0, 2)
        assert any(x.campo == "firmas" for x in svc.cambios(m))


def test_link_del_aviso_firma_la_minuta(app, client, monkeypatch):
    from app.extensions import db
    from app.models import User
    from app.services import accion_link_service as accion_svc
    from app.services import minuta_reunion_service as svc

    with app.app_context():
        u = User(username="pytest_mr_link", password_hash="x", activo=True, rol="sgi", nombre_completo="Ruiz, Eva")
        db.session.add(u)
        db.session.flush()
        m, errs = svc.crear({"motivo": "M", "fecha": "05/11/2026", "horario": "9", "lugar": "L", "desarrollo": "D",
                             "participantes": [{"participante": "Ruiz, Eva", "sector": "SGC", "asistencia": "Presente"}],
                             "acciones": [{"accion": "A", "responsable": "Ruiz, Eva", "fecha": "06/11/2026"}]}, None)
        assert not errs
        db.session.commit()
        token = accion_svc.crear_token(app, accion_svc.MINUTA_FIRMAR, m.id, user_id=u.id)
        mid = m.id
    html = client.get(f"/accion/{token}").get_data(as_text=True)
    assert "Firmar la minuta" in html
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', html).group(1)
    html = client.post(f"/accion/{token}", data={"csrf_token": tok}).get_data(as_text=True)
    assert "firmaste" in html
    with app.app_context():
        assert svc.firmas(svc.get(mid)) == (1, 1)
