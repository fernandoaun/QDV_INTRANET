"""Almacenamiento local y utilidades para PDFs de reactivos de laboratorio."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.models import LaboratoryReagent
from app.services import shift_handover_service as sh
from app.services.upload_paths import resolve_under_upload_roots, uploads_workspace_root
from app.web.modules.produccion.operativa_context import now_local


def lab_reagents_storage_dir() -> Path:
    p = uploads_workspace_root() / "lab_reagents"
    p.mkdir(parents=True, exist_ok=True)
    return p


def lab_reagent_pdf_relative_path(row: LaboratoryReagent) -> Path:
    return Path("lab_reagents") / row.pdf_stored_filename


def lab_reagent_pdf_resolve_path(row: LaboratoryReagent) -> Path | None:
    return resolve_under_upload_roots(lab_reagent_pdf_relative_path(row))


def lab_reagent_pdf_path(row: LaboratoryReagent) -> Path:
    """Ruta esperada en la raíz de trabajo (puede no existir si el archivo está solo en fallback)."""
    return lab_reagents_storage_dir() / row.pdf_stored_filename


def lab_reagent_pdf_is_readable(row: LaboratoryReagent) -> bool:
    return lab_reagent_pdf_resolve_path(row) is not None


def parse_lab_usage_used_at_iso(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return now_local().isoformat(timespec="seconds")
    try:
        dt = datetime.strptime(s[:16], "%Y-%m-%dT%H:%M")
        return dt.isoformat(timespec="seconds")
    except ValueError as e:
        raise ValueError("Fecha y hora de uso inválidas.") from e


def lab_usage_shift_session_id() -> int | None:
    open_s = sh.get_open_shift_session()
    return int(open_s.id) if open_s is not None else None
