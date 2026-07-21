"""Control de cambios automático en procedimientos SGC."""
from __future__ import annotations

from app.services.sgi_procedimiento_service import (
    _diff_descripcion_cambios,
    build_control_cambios_automatico,
    default_contenido,
)


def test_diff_emision_inicial():
    desc = _diff_descripcion_cambios(
        None,
        {"titulo": "Test", "secciones": {"objeto": "A"}},
        revision_label="Rev. 00",
    )
    assert "Emisión inicial" in desc


def test_diff_detecta_seccion():
    prev = {"titulo": "T", "secciones": {"objeto": "Antes", "alcance": "X"}, "registros": [], "anexos": []}
    curr = {"titulo": "T", "secciones": {"objeto": "Después", "alcance": "X"}, "registros": [], "anexos": []}
    desc = _diff_descripcion_cambios(prev, curr, revision_label="Rev. 01")
    assert "OBJETO" in desc.upper()


def test_build_control_cambios_dos_revisiones(app):
    from app.extensions import db
    from app.models.sgi import SgiDocumento, SgiProcedimientoRevision
    from app.services.sgi_procedimiento_service import create_procedimiento_visual

    with app.app_context():
        doc, rev0, _ = create_procedimiento_visual("PG", 1, "tester", titulo="Doc test")
        assert doc is not None
        rev0.estado = "aprobado"
        rev0.fecha_aprobacion = __import__("datetime").date(2026, 5, 1)
        db.session.commit()

        rev1 = SgiProcedimientoRevision(
            documento_id=doc.id,
            numero_revision=1,
            revision_label="Rev. 01",
            estado="borrador",
            contenido_json='{"titulo":"Doc test","secciones":{"objeto":"Nuevo texto"}}',
        )
        db.session.add(rev1)
        db.session.flush()

        payload = {
            "titulo": "Doc test",
            "secciones": {"objeto": "Nuevo texto", "alcance": "", "definiciones": "", "responsabilidades": "", "desarrollo": "", "referencias": "", "control_registros": "", "anexos": ""},
            "registros": [],
            "anexos": [],
        }
        rows = build_control_cambios_automatico(doc, rev1, payload)
        assert len(rows) == 2
        assert rows[0]["revision_ref"] == "00"
        assert rows[1]["revision_ref"] == "01"
        assert "OBJETO" in rows[1]["descripcion"].upper() or "actualización" in rows[1]["descripcion"].lower()
