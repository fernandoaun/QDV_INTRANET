from __future__ import annotations

import re
from io import BytesIO


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    return m.group(1)


def test_archivo_hub_ok(auth_client):
    r = auth_client.get("/archivo/", follow_redirects=True)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Procedimientos y registros" in body
    assert "Procedimientos" in body


def test_archivo_link_on_home_and_nav(auth_client):
    home = auth_client.get("/", follow_redirects=True)
    assert home.status_code == 200
    html = home.get_data(as_text=True)
    assert "/archivo/" in html
    assert "Proc. y registros" in html
    assert "PROC. Y REGISTROS" in html


def test_archivo_blocked_nonprivileged(mant_client):
    r = mant_client.get("/archivo/", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_archivo_lists_sgi_procedure_and_upload(auth_client, app):
    from app.services import sgi_procedimiento_service as proc_svc

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", 1, "tester", titulo="CONTROL DE HIGIENE")
        assert err is None
        assert doc is not None and rev is not None
        doc_id, rev_id = doc.id, rev.id
        ok, msg, _ = proc_svc.save_revision_content(
            rev_id,
            {
                "titulo": "CONTROL DE HIGIENE",
                "secciones": {},
                "registros": [
                    {
                        "nombre": "Planilla diaria",
                        "quien_archiva": "Planta",
                        "como": "Papel",
                        "donde": "Oficina",
                        "tiempo_guarda": "1 año",
                        "usuarios": "Operadores",
                        "disposicion_final": "Archivo",
                    }
                ],
                "anexos": [],
            },
            1,
            "tester",
        )
        assert ok, msg
        payload = proc_svc.revision_to_payload(proc_svc.get_revision(rev_id))
        registro_id = payload["registros"][0]["id"]

        doc_po, rev_po, err_po = proc_svc.create_procedimiento_visual(
            "PO", 1, "tester", titulo="CONTROL DE PROCESO"
        )
        assert err_po is None
        assert doc_po is not None and rev_po is not None
        ok_po, msg_po, _ = proc_svc.save_revision_content(
            rev_po.id,
            {
                "titulo": "CONTROL DE PROCESO",
                "secciones": {},
                "registros": [
                    {
                        "nombre": "Parte de producción",
                        "quien_archiva": "Operador",
                        "como": "Papel",
                        "donde": "Sala de control",
                        "tiempo_guarda": "1 año",
                        "usuarios": "Operadores",
                        "disposicion_final": "Archivo",
                    }
                ],
                "anexos": [],
            },
            1,
            "tester",
        )
        assert ok_po, msg_po

    r = auth_client.get("/archivo/")
    assert r.status_code == 200
    home = r.get_data(as_text=True)
    assert "Procedimientos de gestión" in home
    assert "Procedimientos operativos" in home
    assert "CONTROL DE HIGIENE" in home
    assert "PLANILLA DIARIA" in home
    assert "CONTROL DE PROCESO" in home
    assert "PARTE DE PRODUCCIÓN" in home or "PARTE DE PRODUCCION" in home

    r = auth_client.get(f"/archivo/procedimientos/{doc_id}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "PLANILLA DIARIA" in html
    assert "CONTROL DE HIGIENE" in html

    detail = auth_client.get(f"/archivo/procedimientos/{doc_id}/registros/{registro_id}")
    assert detail.status_code == 200
    r = auth_client.post(
        f"/archivo/procedimientos/{doc_id}/registros/{registro_id}/cargar",
        data={
            "csrf_token": _csrf(detail.get_data(as_text=True)),
            "titulo": "Marzo",
            "fecha_documento": "2026-03-01",
            "notas": "escaneo",
            "archivo": (BytesIO(b"%PDF-1.4 test"), "planilla.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Marzo" in r.data
    assert b"planilla.pdf" in r.data

    hub = auth_client.get("/archivo/")
    assert hub.status_code == 200
    hub_html = hub.get_data(as_text=True)
    assert "Marzo" in hub_html
    assert "planilla.pdf" in hub_html
