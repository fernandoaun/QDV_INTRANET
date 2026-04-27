from __future__ import annotations

from io import BytesIO
import re


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_salmuera_analisis_8hs_create_history_and_export(app, auth_client):
    from app.extensions import db
    from app.models import SalmueraAnalisis8hs

    page = auth_client.get("/produccion/reactor")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Análisis 8 hs" in html
    assert "Dureza y Cloro Libre" in html

    resp = auth_client.post(
        "/produccion/reactor",
        data={
            "csrf_token": _csrf(html),
            "action": "guardar_analisis_8hs",
            "dureza_salmuera": "123,4",
            "cloro_libre_salmuera": "0.7",
            "observaciones": "Control pytest",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["registro"]["dureza_salmuera"] == 123.4
    assert payload["registro"]["cloro_libre_salmuera"] == 0.7
    assert payload["status"]["has_records"] is True

    with app.app_context():
        row = db.session.query(SalmueraAnalisis8hs).one()
        assert row.observaciones == "Control pytest"
        assert row.turno in ("N", "M", "T")
        assert row.fecha_hora_iso

    hist = auth_client.get("/produccion/reactor/analisis-8hs/historial")
    assert hist.status_code == 200
    hist_html = hist.get_data(as_text=True)
    assert "Control pytest" in hist_html
    assert "123.4" in hist_html

    xlsx = auth_client.get("/produccion/reactor/analisis-8hs/export.xlsx")
    assert xlsx.status_code == 200
    assert xlsx.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_salmuera_analisis_8hs_requires_numeric_values(auth_client):
    page = auth_client.get("/produccion/reactor")
    assert page.status_code == 200
    resp = auth_client.post(
        "/produccion/reactor",
        data={
            "csrf_token": _csrf(page.get_data(as_text=True)),
            "action": "guardar_analisis_8hs",
            "dureza_salmuera": "",
            "cloro_libre_salmuera": "abc",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["ok"] is False
    assert "Dureza de salmuera es obligatorio" in payload["error"]


def test_salmuera_analisis_8hs_salmuera_page_and_file_upload(app, auth_client, tmp_path):
    from app.extensions import db
    from app.models import SalmueraAnalisis8hs

    app.config["APP_UPLOAD_ROOT"] = str(tmp_path / "uploads")

    page = auth_client.get("/produccion/salmuera")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Análisis 8 hs – Dureza y Cloro Libre" in html
    assert "analisis8DurezaFileDialog" in html

    resp = auth_client.post(
        "/produccion/salmuera",
        data={
            "csrf_token": _csrf(html),
            "action": "guardar_analisis_8hs",
            "dureza_salmuera": "99.5",
            "cloro_libre_salmuera": "0.2",
            "observaciones": "Con archivo",
            "file_dureza": (BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"), "dureza.pdf"),
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200

    with app.app_context():
        row = db.session.query(SalmueraAnalisis8hs).one()
        assert row.file_dureza_path
        assert (tmp_path / "uploads" / row.file_dureza_path).is_file()
        row_id = row.id

    hist = auth_client.get("/produccion/salmuera/analisis-8hs/historial")
    assert hist.status_code == 200
    hist_html = hist.get_data(as_text=True)
    assert "Abrir / ver archivo" in hist_html

    file_resp = auth_client.get(f"/produccion/salmuera/analisis-8hs/{row_id}/archivo/dureza")
    assert file_resp.status_code == 200
    assert file_resp.mimetype == "application/pdf"
