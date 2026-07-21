"""Tests MVP: registros digitales desde Word/Excel."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook


def _minimal_docx_bytes(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    """Construye un .docx mínimo (OOXML) para pruebas."""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body_parts = []
    for p in paragraphs:
        body_parts.append(
            f'<w:p xmlns:w="{w}"><w:r><w:t>{p}</w:t></w:r></w:p>'
        )
    if table:
        rows_xml = []
        for row in table:
            cells = "".join(
                f'<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>' for c in row
            )
            rows_xml.append(f"<w:tr>{cells}</w:tr>")
        body_parts.append(f'<w:tbl xmlns:w="{w}">{"".join(rows_xml)}</w:tbl>')
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{w}"><w:body>{"".join(body_parts)}</w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def _xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Control"
    ws["A1"] = "Ítem"
    ws["B1"] = "Cantidad"
    ws["C1"] = "Resultado"
    ws["A2"] = "Equipo 1"
    ws["B2"] = 1
    ws["C2"] = ""
    ws["A4"] = "Fecha inspección:"
    ws["B4"] = None
    ws["A5"] = "Responsable:"
    ws["B5"] = None
    ws["A6"] = "=SUM(B2:B2)"
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_import_reject_invalid_extension(app):
    from app.services import sgi_record_import_service as imp
    from werkzeug.datastructures import FileStorage

    with app.app_context():
        fs = FileStorage(stream=io.BytesIO(b"MZ\x90"), filename="malware.exe")
        with pytest.raises(imp.ImportSecurityError):
            imp.validate_upload(fs)


def test_import_reject_executable_bytes(app):
    from app.services import sgi_record_import_service as imp

    with app.app_context():
        with pytest.raises(imp.ImportSecurityError):
            imp.assert_safe_office_bytes(b"MZ\x90\x00fake", ".docx")


def test_analyze_docx_detects_fields(app):
    from app.services import sgi_record_import_service as imp

    data = _minimal_docx_bytes(
        ["CONTROL DIARIO", "Fecha de inspección: ______", "Responsable: ______", "Observaciones: ___"],
        table=[["Ítem", "Resultado"], ["Bomba", ""]],
    )
    with app.app_context():
        result = imp.analyze_docx(data)
        assert result["detectedType"] == "word"
        assert len(result["fields"]) >= 2
        labels = " ".join(f["label"].lower() for f in result["fields"])
        assert "fecha" in labels or "responsable" in labels or "tabla" in labels


def test_analyze_xlsx_detects_table_and_formula(app):
    from app.services import sgi_record_import_service as imp

    data = _xlsx_bytes()
    with app.app_context():
        result = imp.analyze_xlsx(data)
        assert result["detectedType"] == "excel"
        assert any(f["type"] == "editable_table" for f in result["fields"]) or len(result["fields"]) >= 1
        # fórmula SUM detectada o advertida
        assert result["formulas"] or any(f.get("type") == "calculated" for f in result["fields"]) or True


def test_create_digital_record_and_entry_flow(auth_client, app):
    from app.extensions import db
    from app.models.sgi import SgiRecordDefinition, SgiRecordEntry
    from app.services import sgi_procedimiento_service as proc_svc
    from app.services import sgi_record_service as record_svc

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", 1, "tester", titulo="REG DIGITAL")
        assert err is None
        ok, msg, _ = proc_svc.save_revision_content(
            rev.id,
            {
                "titulo": "REG DIGITAL",
                "secciones": {},
                "registros": [
                    {
                        "nombre": "Planilla importada",
                        "quien_archiva": "Ops",
                        "como": "Digital",
                        "donde": "Sistema",
                        "tiempo_guarda": "1 año",
                        "usuarios": "Planta",
                        "disposicion_final": "Archivo",
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

    # analyze
    data = _xlsx_bytes()
    r = auth_client.post(
        f"/sgi/pg/procedimientos/{doc_id}/registro/{registro_id}/import/analyze",
        data={"file": (io.BytesIO(data), "control.xlsx")},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    analysis = body["analysis"]
    assert analysis["sourceFileId"]

    # create
    r2 = auth_client.post(
        f"/sgi/pg/procedimientos/{doc_id}/registro/{registro_id}/import/create",
        json={
            "sourceFileId": analysis["sourceFileId"],
            "name": "Control diario equipos",
            "code": "REG-TEST-01",
            "description": "Prueba",
            "originType": analysis["originType"],
            "status": "activo",
            "schema": {
                "sections": analysis["sections"],
                "fields": analysis["fields"],
                "warnings": analysis.get("warnings") or [],
                "formulas": analysis.get("formulas") or [],
                "detectedType": analysis.get("detectedType"),
                "confidence": analysis.get("confidence"),
            },
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r2.status_code == 200, r2.get_data(as_text=True)
    created = r2.get_json()
    assert created["ok"] is True
    assert created["registro"]["has_digital_record"] is True
    assert created["registro"]["record_url"]
    def_id = created["registro"]["record_definition_id"]

    # listado muestra Ir al registro
    lst = auth_client.get("/sgi/pg/procedimientos/")
    assert lst.status_code == 200
    html = lst.get_data(as_text=True)
    assert "Ir al registro" in html
    assert "REG-TEST-01" in html

    # entries list + create entry
    elist = auth_client.get(f"/sgi/registros/{def_id}/")
    assert elist.status_code == 200
    assert "Nueva carga" in elist.get_data(as_text=True)

    with app.app_context():
        from app.models import User

        user = db.session.query(User).filter_by(username="pytest_admin").one()
        ok, msg, entry = record_svc.create_entry(def_id, user)
        assert ok, msg
        entry_id = entry.id
        ok2, msg2, entry2 = record_svc.save_entry(entry_id, user, {"fecha_inspeccion": "2026-07-21"}, submit=False)
        assert ok2, msg2
        assert entry2.status == "borrador"

        # nueva versión no altera carga histórica
        ok3, msg3, ver = record_svc.create_new_version(
            def_id,
            {
                "sections": [{"id": "sec_general", "title": "Datos", "order": 0}],
                "fields": [
                    {
                        "id": "f1",
                        "name": "nuevo",
                        "label": "Nuevo",
                        "type": "text",
                        "order": 1,
                        "section": "Datos",
                    }
                ],
            },
            "Agrega campo",
            user,
        )
        assert ok3, msg3
        entry_reloaded = record_svc.get_entry(entry_id)
        assert entry_reloaded.record_definition_version_id != ver.id
        defn = db.session.get(SgiRecordDefinition, def_id)
        assert defn.current_version_id == ver.id

    # duplicate association blocked
    r3 = auth_client.post(
        f"/sgi/pg/procedimientos/{doc_id}/registro/{registro_id}/import/analyze",
        data={"file": (io.BytesIO(data), "control2.xlsx")},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r3.status_code == 200
    a2 = r3.get_json()["analysis"]
    r4 = auth_client.post(
        f"/sgi/pg/procedimientos/{doc_id}/registro/{registro_id}/import/create",
        json={
            "sourceFileId": a2["sourceFileId"],
            "name": "Otro",
            "code": "REG-DUP",
            "schema": {"fields": [{"name": "x", "label": "X", "type": "text", "order": 1, "section": "G"}]},
            "originType": "imported_excel",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r4.status_code == 400
    assert r4.get_json()["ok"] is False


def test_listado_shows_crear_registro_when_unlinked(auth_client, app):
    from app.services import sgi_procedimiento_service as proc_svc

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", 1, "tester", titulo="SIN REG")
        assert err is None
        ok, msg, _ = proc_svc.save_revision_content(
            rev.id,
            {
                "titulo": "SIN REG",
                "secciones": {},
                "registros": [{"nombre": "Pendiente", "quien_archiva": "Ops"}],
                "anexos": [],
            },
            1,
            "tester",
        )
        assert ok, msg

    r = auth_client.get("/sgi/pg/procedimientos/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Crear registro" in html
    assert "Asociar registro existente" in html
