"""
PDFs de referencia junto a campos analíticos (ícono erlenmeyer).

Cada documento tiene una clave estable en `app_uploaded_documents.doc_key`.
El archivo de Hipo conc histórico sigue en `uploads/hipo_conc/`; el resto en `uploads/analysis_ref/<doc_key>/`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import current_app

from app.extensions import db
from app.models import AppUploadedDocument
from sqlalchemy import select

# Clave original (no renombrar; ya puede existir fila y archivos en disco).
HIPO_CONC_PDF_DOC_KEY = "salmuera_hipo_conc_pdf"

_ANALYSIS_REF_PDF_REGISTRY: dict[str, dict[str, Any]] = {
    HIPO_CONC_PDF_DOC_KEY: {
        "permission": "salmuera",
        "redirect_endpoint": "produccion.salmuera",
        "modal_title": "Hipo conc",
        "flash_label": "Hipo conc",
        "legacy_hipo_dir": True,
    },
    "salmuera_hipo_exceso_soda_pdf": {
        "permission": "salmuera",
        "redirect_endpoint": "produccion.salmuera",
        "modal_title": "Hipo exceso soda",
        "flash_label": "Hipo exceso soda",
        "legacy_hipo_dir": False,
    },
    "salmuera_soda_conc_pdf": {
        "permission": "salmuera",
        "redirect_endpoint": "produccion.salmuera",
        "modal_title": "Soda conc",
        "flash_label": "Soda conc",
        "legacy_hipo_dir": False,
    },
    "reactor_exceso_naoh_pdf": {
        "permission": "reactor",
        "redirect_endpoint": "produccion.reactor",
        "modal_title": "Exceso NaOH",
        "flash_label": "Exceso NaOH",
        "legacy_hipo_dir": False,
    },
    "reactor_exceso_na2co3_pdf": {
        "permission": "reactor",
        "redirect_endpoint": "produccion.reactor",
        "modal_title": "Exceso Na₂CO₃",
        "flash_label": "Exceso Na₂CO₃",
        "legacy_hipo_dir": False,
    },
    "agua_dureza_pdf": {
        "permission": "agua",
        "redirect_endpoint": "produccion.agua",
        "modal_title": "Dureza",
        "flash_label": "Dureza",
        "legacy_hipo_dir": False,
    },
}


def analysis_ref_pdf_doc_keys() -> frozenset[str]:
    return frozenset(_ANALYSIS_REF_PDF_REGISTRY.keys())


def analysis_ref_pdf_meta(doc_key: str) -> dict[str, Any] | None:
    return _ANALYSIS_REF_PDF_REGISTRY.get(doc_key)


def _legacy_hipo_conc_dir() -> Path:
    p = Path(current_app.instance_path) / "uploads" / "hipo_conc"
    p.mkdir(parents=True, exist_ok=True)
    return p


def analysis_ref_pdf_storage_dir(doc_key: str) -> Path:
    meta = _ANALYSIS_REF_PDF_REGISTRY.get(doc_key)
    if meta and meta.get("legacy_hipo_dir"):
        return _legacy_hipo_conc_dir()
    p = Path(current_app.instance_path) / "uploads" / "analysis_ref" / doc_key
    p.mkdir(parents=True, exist_ok=True)
    return p


def analysis_ref_pdf_file_exists(doc_key: str, row: AppUploadedDocument | None) -> bool:
    if row is None:
        return False
    fp = analysis_ref_pdf_storage_dir(doc_key) / row.stored_filename
    return fp.is_file()


def analysis_ref_pdf_present_map(doc_keys: tuple[str, ...]) -> dict[str, bool]:
    """Mapa doc_key -> hay PDF válido en disco (para plantillas)."""
    out: dict[str, bool] = {k: False for k in doc_keys}
    if not doc_keys:
        return out
    rows = db.session.scalars(select(AppUploadedDocument).where(AppUploadedDocument.doc_key.in_(doc_keys))).all()
    by_key = {r.doc_key: r for r in rows}
    for k in doc_keys:
        out[k] = analysis_ref_pdf_file_exists(k, by_key.get(k))
    return out


SALMUERA_ANALYSIS_REF_SPECS: tuple[dict[str, str], ...] = (
    {"doc_key": HIPO_CONC_PDF_DOC_KEY, "modal_id": "analysisRefModalSalmueraHipoConc", "label": "Hipo conc"},
    {"doc_key": "salmuera_hipo_exceso_soda_pdf", "modal_id": "analysisRefModalSalmueraHipoExcesoSoda", "label": "Hipo exceso soda"},
    {"doc_key": "salmuera_soda_conc_pdf", "modal_id": "analysisRefModalSalmueraSodaConc", "label": "Soda conc"},
)

REACTOR_ANALYSIS_REF_SPECS: tuple[dict[str, str], ...] = (
    {"doc_key": "reactor_exceso_naoh_pdf", "modal_id": "analysisRefModalReactorExcesoNaoh", "label": "Exceso NaOH"},
    {"doc_key": "reactor_exceso_na2co3_pdf", "modal_id": "analysisRefModalReactorExcesoNa2co3", "label": "Exceso Na₂CO₃"},
)

AGUA_ANALYSIS_REF_SPECS: tuple[dict[str, str], ...] = (
    {"doc_key": "agua_dureza_pdf", "modal_id": "analysisRefModalAguaDureza", "label": "Dureza"},
)


def analysis_ref_ui_rows(specs: tuple[dict[str, str], ...]) -> list[dict[str, Any]]:
    keys = tuple(s["doc_key"] for s in specs)
    present = analysis_ref_pdf_present_map(keys)
    return [{**dict(s), "pdf_present": present[s["doc_key"]]} for s in specs]
