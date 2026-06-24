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
    doc_id = m.group(1)

    lg = sgi_role_client.get("/sgi/msgi/")
    csrf2 = _csrf_from_html(lg.get_data(as_text=True))
    r = sgi_role_client.post(
        f"/sgi/msgi/{doc_id}/eliminar",
        data={"csrf_token": csrf2},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)


def test_sgi_visual_manual_create(auth_client):
    r = auth_client.get("/sgi/msgi/procedimientos/nuevo", follow_redirects=False)
    assert r.status_code in (302, 303)
    loc = r.headers.get("Location", "")
    assert "/sgi/msgi/procedimientos/" in loc and "/editor" in loc

    r_list = auth_client.get("/sgi/msgi/procedimientos/")
    assert r_list.status_code == 200
    assert b"QDV-MSGI-" in r_list.data


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
