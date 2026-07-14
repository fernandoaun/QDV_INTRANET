from __future__ import annotations

import re
import zipfile

import pytest
from werkzeug.security import generate_password_hash


@pytest.fixture
def angel_user(app):
    from app.extensions import db
    from app.models import User
    from app.user_roles import ROLE_SOLO_LECTURA_TOTAL

    with app.app_context():
        u = User(
            username="pytest_angel_sgi",
            password_hash=generate_password_hash("pytest-angel-pw"),
            is_admin=False,
            activo=True,
            rol=ROLE_SOLO_LECTURA_TOTAL,
        )
        db.session.add(u)
        db.session.commit()
        return u.username


@pytest.fixture
def angel_client(client, angel_user):
    lg = client.get("/login")
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = client.post(
        "/login",
        data={
            "username": angel_user,
            "password": "pytest-angel-pw",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    return client


@pytest.fixture
def sgi_perm_user(app):
    from app.extensions import db
    from app.models import PermisoUsuario, User
    from app.user_roles import ROLE_OPERACIONES

    with app.app_context():
        u = User(
            username="pytest_sgi_perm",
            password_hash=generate_password_hash("pytest-sgi-pw"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add(u)
        db.session.flush()
        db.session.add(
            PermisoUsuario(user_id=u.id, permiso="sgi_hub", habilitado=True, puede_editar=False)
        )
        db.session.add(
            PermisoUsuario(user_id=u.id, permiso="sgi_documentos_edit", habilitado=True, puede_editar=True)
        )
        db.session.commit()
        return u.username


@pytest.fixture
def sgi_perm_client(client, sgi_perm_user):
    lg = client.get("/login")
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = client.post(
        "/login",
        data={
            "username": sgi_perm_user,
            "password": "pytest-sgi-pw",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    return client


@pytest.fixture
def sgi_role_user(app):
    from app.extensions import db
    from app.models import PermisoUsuario, User
    from app.user_roles import ROLE_SGI

    with app.app_context():
        u = User(
            username="pytest_sgi_role",
            password_hash=generate_password_hash("pytest-sgi-role-pw"),
            is_admin=False,
            activo=True,
            rol=ROLE_SGI,
        )
        db.session.add(u)
        db.session.flush()
        # Override legacy conflict: SGI debe seguir editando SGI aunque exista esta fila.
        db.session.add(PermisoUsuario(user_id=u.id, permiso="sgi_documentos_edit", habilitado=False, puede_editar=False))
        db.session.commit()
        return u.username


@pytest.fixture
def sgi_role_client(client, sgi_role_user):
    lg = client.get("/login")
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r = client.post(
        "/login",
        data={
            "username": sgi_role_user,
            "password": "pytest-sgi-role-pw",
            "csrf_token": m.group(1),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    return client


def test_sgi_blocked_nonprivileged(mant_client):
    r = mant_client.get("/sgi/", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_sgi_admin_hub_ok(auth_client):
    r = auth_client.get("/sgi/")
    assert r.status_code == 200
    assert b"SGI" in r.data


def test_sgi_angel_hub_ok(angel_client):
    r = angel_client.get("/sgi/")
    assert r.status_code == 200


def test_sgi_angel_cannot_open_create(angel_client):
    r = angel_client.get("/sgi/pg/nuevo", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_sgi_perm_user_list_ok(sgi_perm_client):
    r = sgi_perm_client.get("/sgi/po/")
    assert r.status_code == 200


def _csrf_from_html(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    return m.group(1)


def test_sgi_admin_create_list_export(auth_client):
    r_form = auth_client.get("/sgi/pg/nuevo")
    assert r_form.status_code == 200
    csrf = _csrf_from_html(r_form.get_data(as_text=True))
    r = auth_client.post(
        "/sgi/pg/nuevo",
        data={
            "csrf_token": csrf,
            "codigo": "PG-TEST-001",
            "titulo": "Procedimiento de prueba",
            "revision": "01",
            "estado": "borrador",
            "responsable_elaboracion": "Tester",
            "responsable_aprobacion": "Admin",
            "observaciones": "Nota test",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    r_list = auth_client.get("/sgi/pg/?q=PG-TEST-001")
    assert r_list.status_code == 200
    assert b"PG-TEST-001" in r_list.data

    r_xlsx = auth_client.get("/sgi/pg/export.xlsx")
    assert r_xlsx.status_code == 200
    assert "spreadsheetml" in (r_xlsx.content_type or "")


def test_sgi_perm_user_can_create(sgi_perm_client):
    r_form = sgi_perm_client.get("/sgi/msgi/nuevo")
    assert r_form.status_code == 200
    csrf = _csrf_from_html(r_form.get_data(as_text=True))
    r = sgi_perm_client.post(
        "/sgi/msgi/nuevo",
        data={
            "csrf_token": csrf,
            "codigo": "MSGI-T-01",
            "titulo": "Manual test",
            "revision": "00",
            "estado": "vigente",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)


def test_sgi_role_can_create(sgi_role_client):
    r_form = sgi_role_client.get("/sgi/msgi/nuevo")
    assert r_form.status_code == 200
    csrf = _csrf_from_html(r_form.get_data(as_text=True))
    r = sgi_role_client.post(
        "/sgi/msgi/nuevo",
        data={
            "csrf_token": csrf,
            "codigo": "MSGI-SGI-01",
            "titulo": "Manual SGI editable",
            "revision": "00",
            "estado": "vigente",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)


def test_sgi_perm_user_cannot_delete(sgi_perm_client):
    r_form = sgi_perm_client.get("/sgi/msgi/nuevo")
    csrf = _csrf_from_html(r_form.get_data(as_text=True))
    sgi_perm_client.post(
        "/sgi/msgi/nuevo",
        data={
            "csrf_token": csrf,
            "codigo": "MSGI-DEL-01",
            "titulo": "Para borrar",
            "estado": "borrador",
        },
        follow_redirects=True,
    )
    r_list = sgi_perm_client.get("/sgi/msgi/?q=MSGI-DEL-01")
    html = r_list.get_data(as_text=True)
    m = re.search(r"/sgi/msgi/(\d+)", html)
    assert m is not None
    doc_id = m.group(1)

    lg = sgi_perm_client.get("/sgi/msgi/")
    csrf2 = _csrf_from_html(lg.get_data(as_text=True))
    r = sgi_perm_client.post(
        f"/sgi/msgi/{doc_id}/eliminar",
        data={"csrf_token": csrf2},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)


def test_sgi_role_can_delete(sgi_role_client):
    from app.extensions import db
    from app.models.sgi import SgiDocumento

    r_form = sgi_role_client.get("/sgi/msgi/nuevo")
    csrf = _csrf_from_html(r_form.get_data(as_text=True))
    sgi_role_client.post(
        "/sgi/msgi/nuevo",
        data={
            "csrf_token": csrf,
            "codigo": "MSGI-SGI-DEL-01",
            "titulo": "Eliminar como SGI",
            "estado": "borrador",
        },
        follow_redirects=True,
    )
    r_list = sgi_role_client.get("/sgi/msgi/?q=MSGI-SGI-DEL-01")
    html = r_list.get_data(as_text=True)
    m = re.search(r"/sgi/msgi/(\d+)", html)
    assert m is not None
    doc_id = int(m.group(1))

    lg = sgi_role_client.get("/sgi/msgi/")
    csrf2 = _csrf_from_html(lg.get_data(as_text=True))
    r = sgi_role_client.post(
        f"/sgi/msgi/{doc_id}/eliminar",
        data={"csrf_token": csrf2},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with sgi_role_client.application.app_context():
        row = db.session.get(SgiDocumento, doc_id)
        assert row is not None
        assert row.deleted_at is not None
        assert row.codigo_archivado == "MSGI-SGI-DEL-01"

    r_list2 = sgi_role_client.get("/sgi/msgi/")
    assert f"/sgi/msgi/{doc_id}".encode() not in r_list2.data


def test_sgi_visual_manual_create(auth_client):
    r = auth_client.get("/sgi/msgi/procedimientos/nuevo", follow_redirects=False)
    assert r.status_code in (302, 303)
    loc = r.headers.get("Location", "")
    assert "/sgi/msgi/procedimientos/" in loc and "/editor" in loc

    r_list = auth_client.get("/sgi/msgi/procedimientos/")
    assert r_list.status_code == 200
    assert b"QDV-MSGI-" in r_list.data


def test_sgi_visual_procedure_soft_delete_and_restore(auth_client):
    from app.extensions import db
    from app.models.sgi import SgiDocumento

    auth_client.get("/sgi/pg/procedimientos/nuevo", follow_redirects=True)
    r_list = auth_client.get("/sgi/pg/procedimientos/")
    html = r_list.get_data(as_text=True)
    m = re.search(r"/sgi/pg/procedimientos/(\d+)/editor", html)
    assert m is not None
    doc_id = int(m.group(1))
    codigo_m = re.search(r"<strong>(QDV-PG-\d+)</strong>", html)
    assert codigo_m is not None
    codigo = codigo_m.group(1)

    lg = auth_client.get("/sgi/pg/procedimientos/")
    csrf = _csrf_from_html(lg.get_data(as_text=True))
    r_del = auth_client.post(
        f"/sgi/pg/procedimientos/{doc_id}/eliminar",
        data={"csrf_token": csrf},
        follow_redirects=True,
    )
    assert r_del.status_code == 200
    assert b"movido a la papelera" in r_del.data.lower() or b"papelera" in r_del.data.lower()

    r_vigentes = auth_client.get("/sgi/pg/procedimientos/")
    assert codigo.encode() not in r_vigentes.data

    r_papelera = auth_client.get("/sgi/pg/procedimientos/eliminados/")
    assert r_papelera.status_code == 200
    assert codigo.encode() in r_papelera.data

    csrf2 = _csrf_from_html(r_papelera.get_data(as_text=True))
    r_rec = auth_client.post(
        f"/sgi/pg/procedimientos/{doc_id}/recuperar",
        data={"csrf_token": csrf2},
        follow_redirects=True,
    )
    assert r_rec.status_code == 200
    assert codigo.encode() in auth_client.get("/sgi/pg/procedimientos/").data

    with auth_client.application.app_context():
        row = db.session.get(SgiDocumento, doc_id)
        assert row is not None
        assert row.deleted_at is None
        assert row.codigo == codigo


def test_sgi_msgi_firma_gerente_upload(sgi_perm_client, app):
    from io import BytesIO

    from app.extensions import db
    from app.models.sgi import SgiDocumento
    from app.services import sgi_procedimiento_service as proc_svc

    r_form = sgi_perm_client.get("/sgi/msgi/nuevo")
    csrf = _csrf_from_html(r_form.get_data(as_text=True))
    sgi_perm_client.post(
        "/sgi/msgi/nuevo",
        data={
            "csrf_token": csrf,
            "codigo": "MSGI-FIRMA-01",
            "titulo": "Manual con firma",
            "estado": "borrador",
        },
        follow_redirects=True,
    )
    r_list = sgi_perm_client.get("/sgi/msgi/?q=MSGI-FIRMA-01")
    m = re.search(r"/sgi/msgi/(\d+)", r_list.get_data(as_text=True))
    assert m is not None
    doc_id = int(m.group(1))

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r_det = sgi_perm_client.get(f"/sgi/msgi/{doc_id}")
    csrf2 = _csrf_from_html(r_det.get_data(as_text=True))
    r_up = sgi_perm_client.post(
        f"/sgi/msgi/{doc_id}/firma-gerente",
        data={"csrf_token": csrf2, "firma": (BytesIO(png), "firma.png")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r_up.status_code in (302, 303)

    with app.app_context():
        doc = db.session.get(SgiDocumento, doc_id)
        assert doc is not None
        assert proc_svc.firma_gerente_relative_path(doc_id) is not None

    r_img = sgi_perm_client.get(f"/sgi/msgi/{doc_id}/firma-gerente")
    assert r_img.status_code == 200
    assert r_img.mimetype and "image" in r_img.mimetype


def test_sgi_visual_procedure_create(auth_client):
    r = auth_client.get("/sgi/pg/procedimientos/nuevo", follow_redirects=False)
    assert r.status_code in (302, 303)
    loc = r.headers.get("Location", "")
    assert "/sgi/pg/procedimientos/" in loc and "/editor" in loc

    r_list = auth_client.get("/sgi/pg/procedimientos/")
    assert r_list.status_code == 200
    assert b"QDV-PG-" in r_list.data


def test_sgi_visual_procedure_angel_cannot_create(angel_client):
    r = angel_client.get("/sgi/pg/procedimientos/nuevo", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_sgi_parse_form_uppercases_codigo_and_titulo():
    from app.services import sgi_service as svs

    parsed, err = svs._parse_form(
        {
            "codigo": "pg-test-001",
            "titulo": "procedimiento de prueba",
            "estado": "borrador",
        },
        tipo_fijo="PG",
    )
    assert err is None
    assert parsed is not None
    assert parsed["codigo"] == "PG-TEST-001"
    assert parsed["titulo"] == "PROCEDIMIENTO DE PRUEBA"


def test_sgi_parse_form_uppercases_responsables():
    from app.services import sgi_service as svs

    parsed, err = svs._parse_form(
        {
            "codigo": "PG-01",
            "titulo": "Test",
            "estado": "borrador",
            "responsable_elaboracion": "area produccion",
            "responsable_aprobacion": "gerencia",
        },
        tipo_fijo="PG",
    )
    assert err is None
    assert parsed["responsable_elaboracion"] == "AREA PRODUCCION"
    assert parsed["responsable_aprobacion"] == "GERENCIA"


def test_ensure_documento_nombres_mayusculas(app):
    from app.extensions import db
    from app.models.sgi import SgiDocumento
    from app.services import sgi_service as svs

    with app.app_context():
        doc = SgiDocumento(
            tipo="PG",
            codigo="pg-aux-01",
            titulo="titulo mixto",
            revision="",
            estado="borrador",
        )
        db.session.add(doc)
        db.session.commit()
        assert svs.ensure_documento_nombres_mayusculas(doc) is True
        db.session.commit()
        db.session.refresh(doc)
        assert doc.codigo == "PG-AUX-01"
        assert doc.titulo == "TITULO MIXTO"
        doc.responsable_elaboracion = "juan perez"
        doc.responsable_revision = "maria lopez"
        doc.responsable_aprobacion = "dir. calidad"
        assert svs.ensure_documento_nombres_mayusculas(doc) is True
        db.session.commit()
        db.session.refresh(doc)
        assert doc.responsable_elaboracion == "JUAN PEREZ"
        assert doc.responsable_revision == "MARIA LOPEZ"
        assert doc.responsable_aprobacion == "DIR. CALIDAD"
        db.session.delete(doc)
        db.session.commit()


def test_sgi_registro_modulo_persist_and_links(auth_client, app):
    from app.services import sgi_procedimiento_service as proc_svc

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", 1, "tester", titulo="REGISTRO MODULO")
        assert err is None
        assert doc is not None and rev is not None
        doc_id, rev_id = doc.id, rev.id

        ok, msg, _ = proc_svc.save_revision_content(
            rev_id,
            {
                "titulo": "REGISTRO MODULO",
                "secciones": {},
                "registros": [
                    {
                        "nombre": "Planilla salmuera",
                        "quien_archiva": "Operaciones",
                        "como": "Digital",
                        "donde": "Sistema",
                        "tiempo_guarda": "5 años",
                        "usuarios": "Planta",
                        "disposicion_final": "Archivo",
                        "modulo": "salmuera",
                    }
                ],
                "anexos": [],
            },
            1,
            "tester",
        )
        assert ok, msg
        payload = proc_svc.revision_to_payload(proc_svc.get_revision(rev_id))
        assert len(payload["registros"]) == 1
        rg = payload["registros"][0]
        assert rg["modulo"] == "salmuera"
        assert "HIPOCLORITO" in (rg.get("modulo_label") or "").upper()
        assert "/salmuera" in (rg.get("blank_url") or "")
        assert "historial" in (rg.get("filled_url") or "")

        catalog = proc_svc.registro_modulos_catalog_for_js()
        assert "salmuera" in catalog
        assert "/salmuera" in catalog["salmuera"]["blank_url"]

    r_editor = auth_client.get(f"/sgi/pg/procedimientos/{doc_id}/editor/{rev_id}")
    assert r_editor.status_code == 200
    html = r_editor.get_data(as_text=True)
    assert "modulosRegistro" in html
    assert "salmuera" in html
    assert "/salmuera" in html

    r_vista = auth_client.get(f"/sgi/pg/procedimientos/{doc_id}/vista/{rev_id}")
    assert r_vista.status_code == 200
    vista = r_vista.get_data(as_text=True)
    assert "Ver en blanco" in vista
    assert "Ir al módulo" in vista or "Ver módulo" in vista
    assert "/salmuera" in vista
    assert "PLANILLA SALMUERA" in vista


def test_sgi_listado_asociar_desasociar_modulo(auth_client, app):
    from app.services import sgi_procedimiento_service as proc_svc

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", 1, "tester", titulo="ASOCIAR MODULO")
        assert err is None
        ok, msg, _ = proc_svc.save_revision_content(
            rev.id,
            {
                "titulo": "ASOCIAR MODULO",
                "secciones": {},
                "registros": [
                    {
                        "nombre": "Registro asociable",
                        "quien_archiva": "Ops",
                        "como": "Digital",
                        "donde": "Sistema",
                        "tiempo_guarda": "1 año",
                        "usuarios": "Planta",
                        "disposicion_final": "Archivo",
                        "modulo": "",
                    }
                ],
                "anexos": [],
            },
            1,
            "tester",
        )
        assert ok, msg
        payload = proc_svc.revision_to_payload(proc_svc.get_revision(rev.id))
        registro_id = payload["registros"][0]["id"]
        doc_id = doc.id

    r_list = auth_client.get("/sgi/pg/procedimientos/")
    assert r_list.status_code == 200
    html = r_list.get_data(as_text=True)
    assert "Asociar" in html
    assert "REGISTRO ASOCIABLE" in html

    r_asoc = auth_client.post(
        f"/sgi/pg/procedimientos/{doc_id}/registro/{registro_id}/modulo",
        json={"modulo": "salmuera"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r_asoc.status_code == 200
    body = r_asoc.get_json()
    assert body["ok"] is True
    assert body["registro"]["modulo"] == "salmuera"
    assert "/salmuera" in body["registro"]["blank_url"]

    r_list2 = auth_client.get("/sgi/pg/procedimientos/")
    html2 = r_list2.get_data(as_text=True)
    assert "Desasociar" in html2
    assert "Ver en blanco" in html2
    assert "Ir al módulo" in html2

    r_des = auth_client.post(
        f"/sgi/pg/procedimientos/{doc_id}/registro/{registro_id}/modulo",
        json={"modulo": ""},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r_des.status_code == 200
    assert r_des.get_json()["ok"] is True
    assert r_des.get_json()["registro"]["modulo"] == ""

    r_list3 = auth_client.get("/sgi/pg/procedimientos/")
    html3 = r_list3.get_data(as_text=True)
    assert "Asociar" in html3


def test_sgi_listado_muestra_registros_punto_7(auth_client, app):
    from app.services import sgi_procedimiento_service as proc_svc

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", 1, "tester", titulo="LISTADO REGISTROS")
        assert err is None
        ok, msg, _ = proc_svc.save_revision_content(
            rev.id,
            {
                "titulo": "LISTADO REGISTROS",
                "secciones": {},
                "registros": [
                    {
                        "nombre": "Registro listado demo",
                        "quien_archiva": "Ops",
                        "como": "Digital",
                        "donde": "Sistema",
                        "tiempo_guarda": "1 año",
                        "usuarios": "Planta",
                        "disposicion_final": "Archivo",
                        "modulo": "reactor",
                    }
                ],
                "anexos": [],
            },
            1,
            "tester",
        )
        assert ok, msg
        codigo = doc.codigo

    r_list = auth_client.get("/sgi/pg/procedimientos/")
    assert r_list.status_code == 200
    html = r_list.get_data(as_text=True)
    assert codigo in html
    assert "REGISTRO LISTADO DEMO" in html
    assert "sgi-list-registro" in html
    assert "Ver en blanco" in html
    assert "Ir al módulo" in html
    assert "/reactor" in html
    assert "Desasociar" in html


def test_sgi_asociar_modulo_solo_sgi_o_admin(sgi_perm_client, app):
    """Operaciones con sgi_documentos_edit no puede asociar; solo admin/perfil SGI."""
    from app.services import sgi_procedimiento_service as proc_svc

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", 1, "tester", titulo="PERM ASOCIAR")
        assert err is None
        ok, msg, _ = proc_svc.save_revision_content(
            rev.id,
            {
                "titulo": "PERM ASOCIAR",
                "secciones": {},
                "registros": [
                    {
                        "nombre": "Registro bloqueado",
                        "quien_archiva": "Ops",
                        "como": "Digital",
                        "donde": "Sistema",
                        "tiempo_guarda": "1 año",
                        "usuarios": "Planta",
                        "disposicion_final": "Archivo",
                        "modulo": "",
                    }
                ],
                "anexos": [],
            },
            1,
            "tester",
        )
        assert ok, msg
        payload = proc_svc.revision_to_payload(proc_svc.get_revision(rev.id))
        registro_id = payload["registros"][0]["id"]
        doc_id = doc.id

    r = sgi_perm_client.post(
        f"/sgi/pg/procedimientos/{doc_id}/registro/{registro_id}/modulo",
        json={"modulo": "salmuera"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 403
    assert r.get_json()["ok"] is False

    r_list = sgi_perm_client.get("/sgi/pg/procedimientos/")
    assert r_list.status_code == 200
    html = r_list.get_data(as_text=True)
    assert "Asociar" not in html or "btn-asociar-modulo" not in html


def test_msgi_anexo_codigo_auto():
    from app.models.sgi import TIPO_MSGI, TIPO_PG
    from app.services.sgi_procedimiento_service import anexo_codigo_auto, int_to_roman

    assert int_to_roman(1) == "I"
    assert int_to_roman(4) == "IV"
    assert anexo_codigo_auto(TIPO_MSGI, 0, "QDV-MSGI-01") == "QDV-ANEXO I"
    assert anexo_codigo_auto(TIPO_MSGI, 3, "QDV-MSGI-01") == "QDV-ANEXO IV"
    assert anexo_codigo_auto(TIPO_PG, 0, "QDV-PG-01") == "QDV-PG-01-A01"


def test_ensure_msgi_documentos(app, tmp_path):
    from app.extensions import db
    from app.models.sgi import SgiDocumento
    from app.services import sgi_procedimiento_service as proc_svc

    src = tmp_path / "politica.docx"
    src.write_bytes(b"docx-test")
    catalog = (
        {
            "codigo": "QDV-ANEXO I",
            "nombre": "POLÍTICA CSSA",
            "revision": "Rev. 00",
            "fecha_vigencia": None,
            "tipo_contenido": "documento",
            "archivo": src,
        },
    )

    with app.app_context():
        docs, logs = proc_svc.ensure_msgi_documentos(actor_label="test", catalog=catalog)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.codigo == "QDV-ANEXO I"
        assert doc.titulo == "POLÍTICA CSSA"
        assert doc.tipo_contenido == "documento"
        assert doc.created_by_id is None
        rev = proc_svc.revision_actual(doc)
        assert rev is not None
        assert rev.anexos.count() == 0
        assert any("documento visual" in line.lower() for line in logs)

        docs2, logs2 = proc_svc.ensure_msgi_documentos(actor_label="test", catalog=catalog)
        assert docs2[0].id == doc.id
        assert len(logs2) >= 1

        for r in list(doc.revisiones_proc):
            db.session.delete(r)
        db.session.delete(doc)
        db.session.commit()


def test_msgi_vista_documento_especial_muestra_adjunto(auth_client, app, tmp_path):
    from app.extensions import db
    from app.services import sgi_procedimiento_service as proc_svc
    from app.services.upload_paths import uploads_workspace_root

    src = tmp_path / "politica.pdf"
    src.write_bytes(b"%PDF-1.4 test")
    catalog = (
        {
            "codigo": "QDV-ANEXO I",
            "nombre": "POLÍTICA CSSA",
            "revision": "Rev. 00",
            "fecha_vigencia": None,
            "tipo_contenido": "documento",
            "archivo": src,
        },
    )

    with app.app_context():
        docs, _ = proc_svc.ensure_msgi_documentos(actor_label="test", catalog=catalog)
        doc = docs[0]
        assert doc.archivo_path
        doc_id = doc.id

    r = auth_client.get(f"/sgi/msgi/procedimientos/{doc_id}/vista")
    assert r.status_code == 200
    assert b"sgi-anexo-view-pdf" in r.data
    assert b"sgi-proc-workspace" not in r.data

    r_editor = auth_client.get(f"/sgi/msgi/procedimientos/{doc_id}/editor")
    assert r_editor.status_code == 200
    assert b"sgi-anexo-view-pdf" in r_editor.data
    assert b"sgi-proc-workspace" not in r_editor.data
    assert b"Documento adjunto" in r_editor.data

    with app.app_context():
        import shutil

        from app.models.sgi import SgiDocumento

        doc = db.session.get(SgiDocumento, doc_id)
        for rev in list(doc.revisiones_proc):
            db.session.delete(rev)
        db.session.delete(doc)
        db.session.commit()
        shutil.rmtree(uploads_workspace_root().joinpath("sgi", str(doc_id)), ignore_errors=True)


def test_msgi_editor_foda_muestra_adjunto(auth_client, app, tmp_path):
    from app.extensions import db
    from app.models.sgi import SgiDocumento
    from app.services import sgi_procedimiento_service as proc_svc
    from app.services.upload_paths import uploads_workspace_root
    import shutil

    src = tmp_path / "foda.pdf"
    src.write_bytes(b"%PDF-1.4 test")
    catalog = (
        {
            "codigo": "QDV-ANEXO IV",
            "nombre": "ANÁLISIS FODA",
            "revision": "Rev. 00",
            "fecha_vigencia": None,
            "tipo_contenido": "documento",
            "archivo": src,
        },
    )

    with app.app_context():
        docs, _ = proc_svc.ensure_msgi_documentos(actor_label="test", catalog=catalog)
        doc = docs[0]
        assert doc.archivo_path
        doc_id = doc.id

    r_editor = auth_client.get(f"/sgi/msgi/procedimientos/{doc_id}/editor")
    assert r_editor.status_code == 200
    assert b"sgi-anexo-view-pdf" in r_editor.data
    assert b"sgi-proc-workspace" not in r_editor.data
    assert b"Documento adjunto" in r_editor.data

    r_vista = auth_client.get(f"/sgi/msgi/procedimientos/{doc_id}/vista")
    assert r_vista.status_code == 200
    assert b"sgi-anexo-view-pdf" in r_vista.data
    assert b"sgi-proc-workspace" not in r_vista.data

    with app.app_context():
        doc = db.session.get(SgiDocumento, doc_id)
        for rev in list(doc.revisiones_proc):
            db.session.delete(rev)
        db.session.delete(doc)
        db.session.commit()
        shutil.rmtree(uploads_workspace_root().joinpath("sgi", str(doc_id)), ignore_errors=True)


def test_msgi_editor_mapa_muestra_adjunto(auth_client, app, tmp_path):
    from app.extensions import db
    from app.models.sgi import SgiDocumento
    from app.services import sgi_procedimiento_service as proc_svc
    from app.services.upload_paths import uploads_workspace_root
    import shutil

    src = tmp_path / "mapa.png"
    src.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    catalog = (
        {
            "codigo": "QDV-ANEXO III",
            "nombre": "MAPA DE PROCESOS",
            "revision": "Rev. 00",
            "fecha_vigencia": None,
            "tipo_contenido": "archivo",
            "archivo": src,
        },
    )

    with app.app_context():
        docs, _ = proc_svc.ensure_msgi_documentos(actor_label="test", catalog=catalog)
        doc = docs[0]
        assert doc.archivo_path
        doc_id = doc.id

    r_editor = auth_client.get(f"/sgi/msgi/procedimientos/{doc_id}/editor")
    assert r_editor.status_code == 200
    assert b"sgi-anexo-view-img" in r_editor.data
    assert b"sgi-proc-workspace" not in r_editor.data
    assert b"Documento adjunto" in r_editor.data

    r_vista = auth_client.get(f"/sgi/msgi/procedimientos/{doc_id}/vista")
    assert r_vista.status_code == 200
    assert b"sgi-anexo-view-img" in r_vista.data

    with app.app_context():
        doc = db.session.get(SgiDocumento, doc_id)
        for rev in list(doc.revisiones_proc):
            db.session.delete(rev)
        db.session.delete(doc)
        db.session.commit()
        shutil.rmtree(uploads_workspace_root().joinpath("sgi", str(doc_id)), ignore_errors=True)


def test_documento_es_especial():
    from app.models.sgi import SgiDocumento
    from app.services.sgi_anexo_service import documento_es_especial

    doc = SgiDocumento(tipo="MSGI", codigo="QDV-ANEXO II", titulo="ORG", tipo_contenido="organigrama")
    assert documento_es_especial(doc) is True
    doc2 = SgiDocumento(tipo="MSGI", codigo="QDV-MSGI-01", titulo="MANUAL", tipo_contenido=None)
    assert documento_es_especial(doc2) is False


def test_anexo_vista_tipo():
    from app.services.sgi_procedimiento_service import anexo_vista_tipo

    assert anexo_vista_tipo("sgi/x/anexos/MAPA.PNG") == "image"
    assert anexo_vista_tipo("sgi/x/anexos/doc.PDF") == "pdf"
    assert anexo_vista_tipo("sgi/x/anexos/org.PPTX") == "office"
    assert anexo_vista_tipo("sgi/x/anexos/pol.DOCX") == "office"


def test_docx_to_anexo_contenido(tmp_path):
    from app.services.sgi_anexo_service import contenido_from_docx

    p = tmp_path / "t.docx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Política de prueba</w:t></w:r></w:p></w:body>
</w:document>""",
        )
    data = contenido_from_docx(p, "POLÍTICA TEST")
    assert "POLÍTICA TEST" in data["titulo"]
    assert "Política de prueba" in data["secciones"]["desarrollo"]


def test_organigrama_tree_users(app):
    from app.extensions import db
    from app.models.user import User
    from app.services.sgi_anexo_service import ORGANIGRAMA_QDV_SPECS, build_default_organigrama_nodes, organigrama_tree

    with app.app_context():
        u = User(username="org_test", password_hash="x", rol="sgi", activo=True, nombre_completo="ORG TEST")
        db.session.add(u)
        db.session.commit()
        nodes = build_default_organigrama_nodes(preserve_users={"asesoria_qhse": u.id})
        assert len(nodes) == len(ORGANIGRAMA_QDV_SPECS)
        assert nodes[0]["id"] == "gerencia_general"
        planta = next(n for n in nodes if n["id"] == "responsable_planta")
        assert planta["parent_id"] == "gerencia_general"
        tree = organigrama_tree(nodes)
        qhse = next((c for c in tree[0]["children"] if c["id"] == "asesoria_qhse"), None)
        assert qhse is not None
        assert qhse["usuario"]["nombre"] == "ORG TEST"
        turno = next((c for c in tree[0]["children"] if c["id"] == "responsable_planta"), None)
        assert turno is not None
        assert any(c["id"] == "operarios_planta" for c in turno["children"][1]["children"])
        db.session.delete(u)
        db.session.commit()


def test_organigrama_layout_complete(app):
    from app.services.sgi_anexo_service import (
        ORGANIGRAMA_QDV_GRID,
        organigrama_ensure_complete_nodes,
        organigrama_layout_items,
        organigrama_tree,
    )

    with app.app_context():
        partial = [{"id": "gerencia_general", "titulo": "GERENCIA GENERAL", "parent_id": None, "user_id": None, "orden": 0}]
        complete = organigrama_ensure_complete_nodes(partial)
        assert len(complete) == len(ORGANIGRAMA_QDV_GRID)
        items = organigrama_layout_items(organigrama_tree(complete))
        assert len(items) == len(ORGANIGRAMA_QDV_GRID)
        assert items[0]["id"] == "gerencia_general"
        assert items[0]["row"] == 1


def test_parse_organigrama_from_pptx():
    from pathlib import Path

    from app.services.sgi_anexo_service import parse_organigrama_from_pptx

    p = Path(__file__).resolve().parents[1] / "data" / "sgi" / "msgi-anexos" / "QDV-ANEXO II Organigrama_Rev.00.pptx"
    if not p.is_file():
        return
    nodes = parse_organigrama_from_pptx(p)
    assert nodes is not None
    assert nodes[0]["titulo"] == "GERENCIA GENERAL"
    assert any(n["titulo"] == "RESPONSABLE DE PLANTA" for n in nodes)


def test_msgi_anexo_view_and_download(auth_client, app):
    from app.extensions import db
    from app.services import sgi_procedimiento_service as proc_svc
    from app.services.upload_paths import uploads_workspace_root

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("MSGI", 1, "test", titulo="MANUAL TEST")
        assert doc is not None and rev is not None
        payload = proc_svc.revision_to_payload(rev)
        payload["anexos"] = [
            {
                "nombre": "MAPA DE PROCESOS",
                "codigo": "QDV-ANEXO III",
                "revision": "Rev. 00",
                "fecha_vigencia": "",
            }
        ]
        proc_svc._sync_child_rows(rev, payload)
        db.session.commit()
        anexo = rev.anexos.first()
        assert anexo is not None

        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        base = uploads_workspace_root() / "sgi" / "procedimientos" / str(doc.id) / str(rev.id) / "anexos"
        base.mkdir(parents=True, exist_ok=True)
        (base / "MAPA.PNG").write_bytes(png)
        anexo.archivo_path = f"sgi/procedimientos/{doc.id}/{rev.id}/anexos/MAPA.PNG"
        db.session.commit()
        anexo_id = anexo.id
        doc_id = doc.id
        rev_id = rev.id

    r_ver = auth_client.get(f"/sgi/msgi/procedimientos/anexo/{anexo_id}/ver")
    assert r_ver.status_code == 200
    assert b"QDV-ANEXO III" in r_ver.data

    r_inline = auth_client.get(f"/sgi/msgi/procedimientos/anexo/{anexo_id}/archivo?inline=1")
    assert r_inline.status_code == 200
    assert r_inline.headers.get("Content-Type", "").startswith("image/")

    r_dl = auth_client.get(f"/sgi/msgi/procedimientos/anexo/{anexo_id}/archivo")
    assert r_dl.status_code == 200
    assert "attachment" in (r_dl.headers.get("Content-Disposition") or "").lower()

    r_vista = auth_client.get(f"/sgi/msgi/procedimientos/{doc_id}/vista/{rev_id}")
    assert r_vista.status_code == 200
    assert b"sgi-anexo-preview-img" in r_vista.data
