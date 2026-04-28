"""
PDFs de referencia junto a campos analíticos (ícono erlenmeyer).

Cada documento tiene una clave estable en `app_uploaded_documents.doc_key`.
En disco, bajo la raíz de uploads (ver ``uploads_workspace_root`` en ``upload_paths``):
- Hipo conc histórico: ``hipo_conc/``
- Resto: ``analysis_ref/<doc_key>/``

En producción sin volumen persistente (p. ej. deploy default en Render), esa carpeta se pierde
al redesplegar; usar ``APP_UPLOAD_ROOT`` apuntando a un disco persistente.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.extensions import db
from app.models import AppUploadedDocument
from app.services.upload_paths import resolve_under_upload_roots, uploads_workspace_root
from sqlalchemy import select

# Clave original (no renombrar; ya puede existir fila y archivos en disco).
HIPO_CONC_PDF_DOC_KEY = "salmuera_hipo_conc_pdf"
ANALISIS_8HS_DUREZA_PDF_DOC_KEY = "salmuera_analisis_8hs_dureza_pdf"
ANALISIS_8HS_CLORO_LIBRE_PDF_DOC_KEY = "salmuera_analisis_8hs_cloro_libre_pdf"

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
    ANALISIS_8HS_DUREZA_PDF_DOC_KEY: {
        "permission": ("salmuera", "reactor"),
        "redirect_endpoint": "produccion.salmuera",
        "modal_title": "Dureza de salmuera",
        "flash_label": "Dureza de salmuera",
        "legacy_hipo_dir": False,
    },
    ANALISIS_8HS_CLORO_LIBRE_PDF_DOC_KEY: {
        "permission": ("salmuera", "reactor"),
        "redirect_endpoint": "produccion.salmuera",
        "modal_title": "Cloro libre en salmuera",
        "flash_label": "Cloro libre en salmuera",
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


def analysis_ref_pdf_relative_file_path(doc_key: str, stored_filename: str) -> Path:
    """Ruta relativa a la raíz ``uploads`` (hipo_conc/... o analysis_ref/...)."""
    meta = _ANALYSIS_REF_PDF_REGISTRY.get(doc_key)
    if meta and meta.get("legacy_hipo_dir"):
        return Path("hipo_conc") / stored_filename
    return Path("analysis_ref") / doc_key / stored_filename


def analysis_ref_pdf_storage_dir(doc_key: str) -> Path:
    """Directorio donde escribir el PDF de este doc_key (solo la raíz de trabajo)."""
    meta = _ANALYSIS_REF_PDF_REGISTRY.get(doc_key)
    base = uploads_workspace_root()
    if meta and meta.get("legacy_hipo_dir"):
        p = base / "hipo_conc"
    else:
        p = base / "analysis_ref" / doc_key
    p.mkdir(parents=True, exist_ok=True)
    return p


def analysis_ref_pdf_resolve_file_path(doc_key: str, row: AppUploadedDocument | None) -> Path | None:
    """Primera ruta en disco donde existe el archivo (raíz persistente + fallbacks)."""
    if row is None:
        return None
    rel = analysis_ref_pdf_relative_file_path(doc_key, row.stored_filename)
    return resolve_under_upload_roots(rel)


def analysis_ref_pdf_file_exists(doc_key: str, row: AppUploadedDocument | None) -> bool:
    return analysis_ref_pdf_resolve_file_path(doc_key, row) is not None


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
    {"doc_key": ANALISIS_8HS_DUREZA_PDF_DOC_KEY, "modal_id": "analysisRefModalAnalisis8Dureza", "label": "Dureza de salmuera"},
    {"doc_key": ANALISIS_8HS_CLORO_LIBRE_PDF_DOC_KEY, "modal_id": "analysisRefModalAnalisis8CloroLibre", "label": "Cloro libre en salmuera"},
)

REACTOR_ANALYSIS_REF_SPECS: tuple[dict[str, str], ...] = (
    {"doc_key": "reactor_exceso_naoh_pdf", "modal_id": "analysisRefModalReactorExcesoNaoh", "label": "Exceso NaOH"},
    {"doc_key": "reactor_exceso_na2co3_pdf", "modal_id": "analysisRefModalReactorExcesoNa2co3", "label": "Exceso Na₂CO₃"},
    {"doc_key": ANALISIS_8HS_DUREZA_PDF_DOC_KEY, "modal_id": "analysisRefModalAnalisis8Dureza", "label": "Dureza de salmuera"},
    {"doc_key": ANALISIS_8HS_CLORO_LIBRE_PDF_DOC_KEY, "modal_id": "analysisRefModalAnalisis8CloroLibre", "label": "Cloro libre en salmuera"},
)

AGUA_ANALYSIS_REF_SPECS: tuple[dict[str, str], ...] = (
    {"doc_key": "agua_dureza_pdf", "modal_id": "analysisRefModalAguaDureza", "label": "Dureza"},
)


def analysis_ref_ui_rows(specs: tuple[dict[str, str], ...]) -> list[dict[str, Any]]:
    keys = tuple(s["doc_key"] for s in specs)
    present = analysis_ref_pdf_present_map(keys)
    return [{**dict(s), "pdf_present": present[s["doc_key"]]} for s in specs]
