"""CRUD de definiciones digitales de registro, cargas y vínculo con procedimientos."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import url_for
from sqlalchemy import func, select
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models.sgi import (
    ASSOC_EXISTING_MODULE,
    ASSOC_IMPORTED_EXCEL,
    ASSOC_IMPORTED_WORD,
    ASSOC_TYPES,
    ENTRY_STATUS_CLOSED,
    ENTRY_STATUS_DRAFT,
    ENTRY_STATUS_SUBMITTED,
    RECORD_STATUS_ACTIVE,
    RECORD_STATUS_DRAFT,
    SgiProcedimientoRegistro,
    SgiRecordAuditLog,
    SgiRecordDefinition,
    SgiRecordDefinitionVersion,
    SgiRecordEntry,
    SgiRecordFile,
)
from app.models.user import User
from app.services import security_audit_service as audit_svc
from app.services import sgi_record_import_service as import_svc
from app.services.upload_paths import uploads_workspace_root

logger = logging.getLogger(__name__)

ORIGIN_LABELS = {
    ASSOC_EXISTING_MODULE: "Módulo existente",
    ASSOC_IMPORTED_WORD: "Archivo Word",
    ASSOC_IMPORTED_EXCEL: "Archivo Excel",
    "manual_form": "Formulario manual",
}

FIELD_TYPES_ALLOWED = {
    "text",
    "textarea",
    "integer",
    "decimal",
    "date",
    "datetime",
    "time",
    "email",
    "phone",
    "percent",
    "currency",
    "yes_no",
    "checkbox",
    "select",
    "multiselect",
    "dropdown",
    "signature",
    "file",
    "image",
    "editable_table",
    "calculated",
    "readonly",
    "system_user",
    "area",
    "equipment",
    "cost_center",
    "observations",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _user_label(user: User | None) -> str:
    if user is None:
        return ""
    return (getattr(user, "username", None) or str(getattr(user, "id", "")))[:256]


def append_record_audit(
    *,
    entity_type: str,
    entity_id: int,
    action: str,
    user: User | None,
    previous: Any = None,
    new: Any = None,
) -> None:
    prev_s = None if previous is None else json.dumps(previous, ensure_ascii=False)[:8000]
    new_s = None if new is None else json.dumps(new, ensure_ascii=False)[:8000]
    row = SgiRecordAuditLog(
        entity_type=(entity_type or "")[:64],
        entity_id=int(entity_id),
        action=(action or "")[:64],
        previous_data=prev_s,
        new_data=new_s,
        user_id=int(user.id) if user is not None else None,
    )
    db.session.add(row)
    try:
        audit_svc.record_event(
            action=f"sgi_record_{action}"[:64],
            module="sgi",
            actor=user,
            entity_type=entity_type,
            entity_id=int(entity_id),
            old_value=prev_s,
            new_value=new_s,
            detail=action,
        )
    except Exception:
        logger.exception("security audit fallo para sgi_record action=%s", action)


def records_storage_dir(definition_id: int | None = None) -> Path:
    base = uploads_workspace_root() / "sgi" / "record_sources"
    if definition_id:
        base = base / str(int(definition_id))
    else:
        base = base / "_pending"
    base.mkdir(parents=True, exist_ok=True)
    return base


def normalize_schema(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    sections_in = data.get("sections") if isinstance(data.get("sections"), list) else []
    fields_in = data.get("fields") if isinstance(data.get("fields"), list) else []
    sections: list[dict[str, Any]] = []
    for i, s in enumerate(sections_in):
        if not isinstance(s, dict):
            continue
        sections.append(
            {
                "id": str(s.get("id") or f"sec_{i}")[:64],
                "title": str(s.get("title") or f"Sección {i + 1}")[:256],
                "order": int(s.get("order") if s.get("order") is not None else i),
            }
        )
    if not sections:
        sections = [{"id": "sec_general", "title": "Datos generales", "order": 0}]

    fields: list[dict[str, Any]] = []
    for i, f in enumerate(fields_in):
        if not isinstance(f, dict):
            continue
        ftype = str(f.get("type") or "text").strip().lower()
        if ftype not in FIELD_TYPES_ALLOWED:
            ftype = "text"
        name = str(f.get("name") or f"campo_{i + 1}").strip()[:64] or f"campo_{i + 1}"
        item: dict[str, Any] = {
            "id": str(f.get("id") or name)[:64],
            "name": name,
            "label": str(f.get("label") or name)[:256],
            "type": ftype,
            "required": bool(f.get("required")),
            "order": int(f.get("order") if f.get("order") is not None else i + 1),
            "section": str(f.get("section") or sections[0]["title"])[:256],
            "defaultValue": f.get("defaultValue"),
            "placeholder": str(f.get("placeholder") or "")[:256],
            "validation": f.get("validation") if isinstance(f.get("validation"), dict) else {},
            "options": [str(o)[:128] for o in (f.get("options") or []) if o is not None][:50],
            "permissions": f.get("permissions")
            if isinstance(f.get("permissions"), dict)
            else {"editableBy": [], "visibleTo": []},
            "mode": str(f.get("mode") or "editable")[:32],
        }
        if f.get("formula"):
            item["formula"] = str(f.get("formula"))[:500]
        if isinstance(f.get("columns"), list):
            cols = []
            for ci, c in enumerate(f.get("columns") or []):
                if not isinstance(c, dict):
                    continue
                cols.append(
                    {
                        "key": str(c.get("key") or f"col_{ci}")[:64],
                        "label": str(c.get("label") or f"Columna {ci + 1}")[:128],
                        "type": str(c.get("type") or "text")[:32],
                        "required": bool(c.get("required")),
                        "options": [str(o)[:128] for o in (c.get("options") or []) if o is not None][:30],
                    }
                )
            item["columns"] = cols
        fields.append(item)
    fields.sort(key=lambda x: int(x.get("order") or 0))
    layout_html = str(data.get("layoutHtml") or data.get("layout_html") or "")
    # Límite defensivo; sin scripts
    if layout_html:
        layout_html = re.sub(r"(?is)<script[^>]*>.*?</script>", "", layout_html)
        layout_html = re.sub(r"(?is)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", layout_html)
        layout_html = layout_html[:200_000]
    return {
        "sections": sections,
        "fields": fields,
        "warnings": [str(w)[:500] for w in (data.get("warnings") or []) if w][:50],
        "formulas": data.get("formulas") if isinstance(data.get("formulas"), list) else [],
        "detectedType": str(data.get("detectedType") or "")[:32],
        "confidence": float(data.get("confidence") or 0),
        "layoutHtml": layout_html,
        "layoutMode": str(data.get("layoutMode") or ("document" if layout_html else "fields"))[:32],
    }


def parse_version_schema(version: SgiRecordDefinitionVersion | None) -> dict[str, Any]:
    if version is None:
        return normalize_schema({})
    try:
        data = json.loads(version.schema_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        ui = json.loads(version.ui_schema_json or "{}")
    except json.JSONDecodeError:
        ui = {}
    if isinstance(ui, dict):
        if ui.get("layoutHtml") and not data.get("layoutHtml"):
            data["layoutHtml"] = ui.get("layoutHtml")
        if ui.get("layoutMode") and not data.get("layoutMode"):
            data["layoutMode"] = ui.get("layoutMode")
    return normalize_schema(data)


def definition_summary(defn: SgiRecordDefinition) -> dict[str, Any]:
    ver = None
    if defn.current_version_id:
        ver = db.session.get(SgiRecordDefinitionVersion, int(defn.current_version_id))
    version_number = ver.version_number if ver else 1
    record_url = ""
    try:
        from flask import current_app, has_request_context

        if has_request_context():
            record_url = url_for("sgi.record_entries_list", definition_id=defn.id)
        else:
            with current_app.test_request_context():
                record_url = url_for("sgi.record_entries_list", definition_id=defn.id)
    except Exception:
        record_url = f"/sgi/registros/{defn.id}/"
    return {
        "id": defn.id,
        "code": defn.code or "",
        "name": defn.name or "",
        "description": defn.description or "",
        "origin_type": defn.origin_type or "",
        "origin_label": ORIGIN_LABELS.get(defn.origin_type or "", defn.origin_type or ""),
        "status": defn.status or "",
        "version": version_number,
        "current_version_id": defn.current_version_id,
        "created_at": defn.created_at.isoformat() if defn.created_at else "",
        "created_by": _user_label(defn.created_by),
        "record_url": record_url,
    }


def enrich_registro_payload(payload: dict[str, Any], reg: SgiProcedimientoRegistro) -> dict[str, Any]:
    """Agrega datos del registro digital al payload del punto 7."""
    out = dict(payload)
    out["association_type"] = (reg.association_type or "").strip()
    out["record_definition_id"] = reg.record_definition_id
    out["has_digital_record"] = bool(reg.record_definition_id)
    out["record_summary"] = None
    out["record_url"] = ""
    if reg.record_definition_id:
        defn = db.session.get(SgiRecordDefinition, int(reg.record_definition_id))
        if defn and defn.deleted_at is None:
            summary = definition_summary(defn)
            out["record_summary"] = summary
            out["record_url"] = summary["record_url"]
            if not out.get("association_type"):
                out["association_type"] = defn.origin_type or ""
    elif reg.modulo:
        out["association_type"] = ASSOC_EXISTING_MODULE
    return out


def analyze_uploaded_file(file: FileStorage, user: User | None) -> tuple[bool, str, dict[str, Any] | None]:
    try:
        ext, original = import_svc.validate_upload(file)
        data = import_svc.read_file_bytes(file)
        import_svc.assert_safe_office_bytes(data, ext)
        analysis = import_svc.analyze_office_bytes(data, ext)
    except import_svc.ImportSecurityError as exc:
        return False, str(exc), None
    except Exception:
        logger.exception("Error analizando archivo de registro")
        return False, "No se pudo interpretar el archivo.", None

    content_hash = import_svc.file_hash(data)
    safe_name = import_svc.safe_storage_name(original, content_hash)
    pending_dir = records_storage_dir(None)
    dest = pending_dir / safe_name
    dest.write_bytes(data)

    rel_path = f"sgi/record_sources/_pending/{safe_name}"
    rf = SgiRecordFile(
        original_name=original[:512],
        safe_name=safe_name[:512],
        extension=ext[:16],
        mime_type=import_svc._MIME_BY_EXT.get(ext, "application/octet-stream")[:128],
        size_bytes=len(data),
        content_hash=content_hash,
        storage_path=rel_path[:1024],
        analysis_status="analyzed",
        uploaded_by_id=int(user.id) if user else None,
    )
    db.session.add(rf)
    db.session.flush()
    append_record_audit(
        entity_type="sgi_record_file",
        entity_id=rf.id,
        action="archivo_analizado",
        user=user,
        new={"original_name": original, "extension": ext, "hash": content_hash},
    )
    db.session.commit()

    schema = normalize_schema(analysis)
    return True, "Archivo analizado.", {
        "sourceFileId": rf.id,
        "detectedType": schema.get("detectedType") or analysis.get("detectedType"),
        "confidence": schema.get("confidence"),
        "warnings": schema.get("warnings") or [],
        "sections": schema.get("sections") or [],
        "fields": schema.get("fields") or [],
        "tables": analysis.get("tables") or [],
        "formulas": schema.get("formulas") or [],
        "layoutHtml": schema.get("layoutHtml") or analysis.get("layoutHtml") or "",
        "layoutMode": schema.get("layoutMode") or "document",
        "suggestedName": analysis.get("suggestedName") or "",
        "suggestedCode": analysis.get("suggestedCode") or "",
        "originType": import_svc.origin_type_for_ext(ext),
        "originalName": original,
        "maxUploadMb": 15,
        "allowedExtensions": [".docx", ".xlsx", ".xls"],
    }


def create_definition_from_analysis(
    *,
    documento_id: int,
    registro_id: int,
    source_file_id: int,
    name: str,
    code: str,
    description: str,
    schema_payload: dict[str, Any],
    origin_type: str,
    status: str,
    user: User | None,
) -> tuple[bool, str, dict[str, Any] | None]:
    reg = db.session.get(SgiProcedimientoRegistro, int(registro_id))
    if reg is None:
        return False, "Registro del procedimiento no encontrado.", None
    rev = reg.proc_revision
    if rev is None or rev.documento_id != int(documento_id):
        return False, "El registro no pertenece a este procedimiento.", None
    if reg.record_definition_id or (reg.modulo or "").strip():
        return False, "Este registro ya está asociado. Desvincule antes de crear otro.", None

    rf = db.session.get(SgiRecordFile, int(source_file_id))
    if rf is None:
        return False, "Archivo fuente no encontrado. Vuelva a analizar el archivo.", None

    ot = (origin_type or "").strip()
    if ot not in (ASSOC_IMPORTED_WORD, ASSOC_IMPORTED_EXCEL):
        ot = ASSOC_IMPORTED_WORD if rf.extension == ".docx" else ASSOC_IMPORTED_EXCEL

    schema = normalize_schema(schema_payload)
    if not schema.get("fields"):
        return False, "La definición debe tener al menos un campo.", None

    st = (status or RECORD_STATUS_ACTIVE).strip().lower()
    if st not in (RECORD_STATUS_ACTIVE, RECORD_STATUS_DRAFT):
        st = RECORD_STATUS_ACTIVE

    code_clean = (code or "").strip().upper()[:64]
    name_clean = (name or "").strip()[:512] or "Registro importado"
    if not code_clean:
        code_clean = f"REG-{documento_id}-{registro_id}"

    try:
        defn = SgiRecordDefinition(
            code=code_clean,
            name=name_clean,
            description=(description or "")[:4000],
            origin_type=ot,
            source_file_id=rf.id,
            status=st,
            created_by_id=int(user.id) if user else None,
            updated_by_id=int(user.id) if user else None,
        )
        db.session.add(defn)
        db.session.flush()

        # Mover archivo pendiente a carpeta definitiva
        src = uploads_workspace_root() / rf.storage_path
        final_dir = records_storage_dir(defn.id)
        dest = final_dir / rf.safe_name
        if src.is_file():
            dest.write_bytes(src.read_bytes())
            try:
                src.unlink(missing_ok=True)
            except OSError:
                pass
        elif not dest.is_file():
            return False, "No se encontró el archivo fuente en almacenamiento.", None
        rf.storage_path = f"sgi/record_sources/{defn.id}/{rf.safe_name}"[:1024]
        # Copia segura (mismo contenido, prefijo)
        safe_copy = final_dir / f"safe_{rf.safe_name}"
        if dest.is_file() and not safe_copy.is_file():
            safe_copy.write_bytes(dest.read_bytes())

        ver = SgiRecordDefinitionVersion(
            record_definition_id=defn.id,
            version_number=1,
            schema_json=json.dumps(schema, ensure_ascii=False),
            ui_schema_json=json.dumps(
                {
                    "layoutMode": schema.get("layoutMode") or "document",
                    "layoutHtml": schema.get("layoutHtml") or "",
                },
                ensure_ascii=False,
            ),
            change_description="Versión inicial desde importación",
            created_by_id=int(user.id) if user else None,
        )
        db.session.add(ver)
        db.session.flush()
        defn.current_version_id = ver.id

        reg.record_definition_id = defn.id
        reg.association_type = ot
        reg.modulo = ""
        if not (reg.nombre or "").strip():
            reg.nombre = name_clean.upper()[:512]

        append_record_audit(
            entity_type="sgi_record_definition",
            entity_id=defn.id,
            action="registro_creado",
            user=user,
            new={"code": code_clean, "name": name_clean, "origin": ot, "procedure_registro_id": reg.id},
        )
        append_record_audit(
            entity_type="sgi_procedimiento_registro",
            entity_id=reg.id,
            action="registro_asociado",
            user=user,
            new={"record_definition_id": defn.id, "association_type": ot},
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Fallo creando definición de registro")
        return False, "No se pudo crear el registro. Intente nuevamente.", None

    from app.services import sgi_procedimiento_service as proc_svc

    return True, "Registro creado y asociado al procedimiento.", enrich_registro_payload(
        proc_svc._registro_row_payload(reg), reg
    )


def unlink_digital_record(
    documento_id: int,
    registro_id: int,
    user: User | None,
) -> tuple[bool, str, dict[str, Any] | None]:
    reg = db.session.get(SgiProcedimientoRegistro, int(registro_id))
    if reg is None:
        return False, "Registro no encontrado.", None
    rev = reg.proc_revision
    if rev is None or rev.documento_id != int(documento_id):
        return False, "El registro no pertenece a este procedimiento.", None
    if not reg.record_definition_id:
        return False, "No hay registro digital vinculado.", None

    prev = reg.record_definition_id
    reg.record_definition_id = None
    reg.association_type = ""
    append_record_audit(
        entity_type="sgi_procedimiento_registro",
        entity_id=reg.id,
        action="registro_desvinculado",
        user=user,
        previous={"record_definition_id": prev},
        new={"record_definition_id": None},
    )
    db.session.commit()

    from app.services import sgi_procedimiento_service as proc_svc

    return True, "Registro desvinculado.", enrich_registro_payload(proc_svc._registro_row_payload(reg), reg)


def get_definition(definition_id: int) -> SgiRecordDefinition | None:
    defn = db.session.get(SgiRecordDefinition, int(definition_id))
    if defn is None or defn.deleted_at is not None:
        return None
    return defn


def list_entries(definition_id: int) -> list[dict[str, Any]]:
    rows = list(
        db.session.scalars(
            select(SgiRecordEntry)
            .where(SgiRecordEntry.record_definition_id == int(definition_id))
            .order_by(SgiRecordEntry.entry_number.desc())
        )
    )
    out = []
    for e in rows:
        out.append(
            {
                "id": e.id,
                "entry_number": e.entry_number,
                "status": e.status,
                "version_id": e.record_definition_version_id,
                "version_number": e.version.version_number if e.version else None,
                "created_at": e.created_at.isoformat() if e.created_at else "",
                "updated_at": e.updated_at.isoformat() if e.updated_at else "",
                "created_by": _user_label(e.created_by),
                "submitted_at": e.submitted_at.isoformat() if e.submitted_at else "",
                "closed_at": e.closed_at.isoformat() if e.closed_at else "",
            }
        )
    return out


def create_entry(definition_id: int, user: User | None, data: dict[str, Any] | None = None) -> tuple[bool, str, SgiRecordEntry | None]:
    defn = get_definition(definition_id)
    if defn is None:
        return False, "Definición de registro no encontrada.", None
    if not defn.current_version_id:
        return False, "El registro no tiene versión activa.", None

    max_num = db.session.scalar(
        select(func.coalesce(func.max(SgiRecordEntry.entry_number), 0)).where(
            SgiRecordEntry.record_definition_id == defn.id
        )
    )
    entry = SgiRecordEntry(
        record_definition_id=defn.id,
        record_definition_version_id=int(defn.current_version_id),
        entry_number=int(max_num or 0) + 1,
        status=ENTRY_STATUS_DRAFT,
        data_json=json.dumps(data if isinstance(data, dict) else {}, ensure_ascii=False),
        created_by_id=int(user.id) if user else None,
        updated_by_id=int(user.id) if user else None,
    )
    db.session.add(entry)
    db.session.flush()
    append_record_audit(
        entity_type="sgi_record_entry",
        entity_id=entry.id,
        action="carga_iniciada",
        user=user,
        new={"entry_number": entry.entry_number, "definition_id": defn.id},
    )
    db.session.commit()
    return True, "Carga creada.", entry


def get_entry(entry_id: int) -> SgiRecordEntry | None:
    return db.session.get(SgiRecordEntry, int(entry_id))


def save_entry(
    entry_id: int,
    user: User | None,
    data: dict[str, Any],
    *,
    submit: bool = False,
    close: bool = False,
) -> tuple[bool, str, SgiRecordEntry | None]:
    entry = get_entry(entry_id)
    if entry is None:
        return False, "Carga no encontrada.", None
    if entry.status == ENTRY_STATUS_CLOSED:
        return False, "La carga está cerrada y no puede modificarse.", None

    prev = entry.data_json
    entry.data_json = json.dumps(data if isinstance(data, dict) else {}, ensure_ascii=False)
    entry.updated_by_id = int(user.id) if user else None
    entry.updated_at = _utc_now()
    action = "borrador_guardado"
    if submit and entry.status == ENTRY_STATUS_DRAFT:
        entry.status = ENTRY_STATUS_SUBMITTED
        entry.submitted_at = _utc_now()
        action = "carga_enviada"
    if close:
        entry.status = ENTRY_STATUS_CLOSED
        entry.closed_at = _utc_now()
        action = "carga_cerrada"
    append_record_audit(
        entity_type="sgi_record_entry",
        entity_id=entry.id,
        action=action,
        user=user,
        previous={"data": prev[:2000] if prev else None, "status": entry.status},
        new={"status": entry.status},
    )
    db.session.commit()
    return True, "Carga guardada.", entry


def create_new_version(
    definition_id: int,
    schema_payload: dict[str, Any],
    change_description: str,
    user: User | None,
) -> tuple[bool, str, SgiRecordDefinitionVersion | None]:
    defn = get_definition(definition_id)
    if defn is None:
        return False, "Definición no encontrada.", None
    schema = normalize_schema(schema_payload)
    max_v = db.session.scalar(
        select(func.coalesce(func.max(SgiRecordDefinitionVersion.version_number), 0)).where(
            SgiRecordDefinitionVersion.record_definition_id == defn.id
        )
    )
    ver = SgiRecordDefinitionVersion(
        record_definition_id=defn.id,
        version_number=int(max_v or 0) + 1,
        schema_json=json.dumps(schema, ensure_ascii=False),
        ui_schema_json="{}",
        change_description=(change_description or "Nueva versión")[:2000],
        created_by_id=int(user.id) if user else None,
    )
    db.session.add(ver)
    db.session.flush()
    prev = defn.current_version_id
    defn.current_version_id = ver.id
    defn.updated_by_id = int(user.id) if user else None
    append_record_audit(
        entity_type="sgi_record_definition",
        entity_id=defn.id,
        action="nueva_version",
        user=user,
        previous={"version_id": prev},
        new={"version_id": ver.id, "version_number": ver.version_number},
    )
    db.session.commit()
    return True, f"Versión {ver.version_number} creada.", ver
