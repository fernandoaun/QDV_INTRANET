"""Generador visual de procedimientos SGI (PG / PO)."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import Select, func, or_, select
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.sgi import (
    ESTADO_APROBADO,
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADO_OBSOLETO,
    ESTADO_VIGENTE,
    PROCEDIMIENTO_SECCIONES,
    SgiDocumento,
    SgiDocumentoHistorial,
    SgiProcedimientoAnexo,
    SgiProcedimientoAprobacion,
    SgiProcedimientoControlCambio,
    SgiProcedimientoRegistro,
    SgiProcedimientoRevision,
    TIPO_PG,
    TIPO_PO,
    TIPOS_PROCEDIMIENTO_VISUAL,
)
from app.models.user import User
from app.services import sgi_service as doc_svc
from app.services.upload_paths import uploads_workspace_root

ACCION_BORRADOR = "guardar_borrador"
ACCION_ENVIAR_REVISION = "enviar_revision"
ACCION_APROBAR = "aprobar"
ACCION_NUEVA_REVISION = "nueva_revision"

_CODIGO_RE = re.compile(r"^QDV-(PG|PO)-(\d+)$", re.IGNORECASE)
_STYLE_ATTR_RE = re.compile(r'\sstyle=(["\'])(.*?)\1', re.IGNORECASE | re.DOTALL)
_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*[^;\"']+(;|$)", re.IGNORECASE)
_FONT_SHORT_RE = re.compile(r"(?<![\w-])font\s*:\s*[^;\"']+(;|$)", re.IGNORECASE)
_FACE_ATTR_RE = re.compile(r'\sface=(["\'])[^"\']*\1', re.IGNORECASE)
_FLOAT_RE = re.compile(r"float\s*:\s*[^;\"']+(;|$)", re.IGNORECASE)
_POSITION_RE = re.compile(r"position\s*:\s*(?:absolute|fixed)[^;\"']*(;|$)", re.IGNORECASE)
_ALIGN_ATTR_RE = re.compile(r'\salign=(["\'])[^"\']*\1', re.IGNORECASE)
_TABLE_DIM_ATTR_RE = re.compile(r'\s(?:width|height)=(["\'])[^"\']*\1', re.IGNORECASE)


def normalize_procedure_html(html: str) -> str:
    """Quita tipografías y estilos de layout problemáticos del HTML de secciones."""
    if not html or not html.strip():
        return html or ""

    def _clean_style(match: re.Match[str]) -> str:
        quote, style = match.group(1), match.group(2)
        style = _FONT_FAMILY_RE.sub("", style)
        style = _FONT_SHORT_RE.sub("", style)
        style = _FLOAT_RE.sub("", style)
        style = _POSITION_RE.sub("", style)
        style = re.sub(r";\s*;", ";", style).strip().strip(";")
        if style:
            return f" style={quote}{style}{quote}"
        return ""

    result = _STYLE_ATTR_RE.sub(_clean_style, html)
    result = _FACE_ATTR_RE.sub("", result)
    result = _ALIGN_ATTR_RE.sub("", result)

    def _normalize_table(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "sgi-proc-content-table" not in tag:
            tag = tag.replace("<table", '<table class="sgi-proc-content-table"', 1)
        tag = _TABLE_DIM_ATTR_RE.sub("", tag)
        return tag

    result = re.sub(r"<table\b[^>]*>", _normalize_table, result, flags=re.IGNORECASE)

    def _normalize_img(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "sgi-proc-content-img" not in tag:
            tag = tag.replace("<img", '<img class="sgi-proc-content-img"', 1)
        tag = _TABLE_DIM_ATTR_RE.sub("", tag)
        return tag

    result = re.sub(r"<img\b[^>]*>", _normalize_img, result, flags=re.IGNORECASE)
    return result


def normalize_procedure_secciones(secciones: dict[str, Any]) -> dict[str, str]:
    return {k: normalize_procedure_html(str(secciones.get(k) or "")) for k, _ in PROCEDIMIENTO_SECCIONES}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _revision_label(num: int) -> str:
    return f"Rev. {num:02d}"


def _parse_revision_num(label: str) -> int:
    m = re.search(r"(\d+)", label or "")
    if m:
        return int(m.group(1))
    return 0


def _normalize_html(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", t).strip()


def _seccion_label_corta(key: str, label: str) -> str:
    if ".-" in label:
        return label.split(".-", 1)[-1].strip()
    return label


def _diff_descripcion_cambios(
    prev_payload: dict[str, Any] | None,
    curr_payload: dict[str, Any],
    *,
    revision_label: str,
) -> str:
    if prev_payload is None:
        return "Emisión inicial del documento."

    cambios: list[str] = []
    if (prev_payload.get("titulo") or "").strip() != (curr_payload.get("titulo") or "").strip():
        cambios.append("título del documento")

    prev_secs = prev_payload.get("secciones") or {}
    curr_secs = curr_payload.get("secciones") or {}
    for key, label in PROCEDIMIENTO_SECCIONES:
        if key in ("control_registros", "anexos"):
            continue
        if _normalize_html(prev_secs.get(key, "")) != _normalize_html(curr_secs.get(key, "")):
            cambios.append(_seccion_label_corta(key, label))

    prev_reg = json.dumps(prev_payload.get("registros") or [], ensure_ascii=False, sort_keys=True)
    curr_reg = json.dumps(curr_payload.get("registros") or [], ensure_ascii=False, sort_keys=True)
    if prev_reg != curr_reg:
        cambios.append("control de registros")

    prev_anx = json.dumps(prev_payload.get("anexos") or [], ensure_ascii=False, sort_keys=True)
    curr_anx = json.dumps(curr_payload.get("anexos") or [], ensure_ascii=False, sort_keys=True)
    if prev_anx != curr_anx:
        cambios.append("anexos")

    if not cambios:
        return f"{revision_label}: revisión sin cambios detectados en el contenido."

    if len(cambios) == 1:
        return f"{revision_label}: actualización en {cambios[0]}."
    return f"{revision_label}: actualización en {', '.join(cambios[:-1])} y {cambios[-1]}."


def _payload_para_diff(rev: SgiProcedimientoRevision, doc: SgiDocumento, contenido: dict[str, Any]) -> dict[str, Any]:
    return {
        "titulo": (contenido.get("titulo") or doc.titulo or "").strip(),
        "secciones": contenido.get("secciones") or {},
        "registros": contenido.get("registros") or [],
        "anexos": contenido.get("anexos") or [],
    }


def _contenido_from_revision(rev: SgiProcedimientoRevision, doc: SgiDocumento) -> dict[str, Any]:
    try:
        data = json.loads(rev.contenido_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return _payload_para_diff(rev, doc, data)


def build_control_cambios_automatico(
    doc: SgiDocumento,
    rev_actual: SgiProcedimientoRevision,
    curr_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Arma el cuadro de control de cambios desde el historial de revisiones y el diff de contenido."""
    revs = list(
        db.session.scalars(
            select(SgiProcedimientoRevision)
            .where(SgiProcedimientoRevision.documento_id == doc.id)
            .order_by(SgiProcedimientoRevision.numero_revision.asc())
        ).all()
    )
    rows: list[dict[str, Any]] = []
    prev_snapshot: dict[str, Any] | None = None

    for rev in revs:
        ref = f"{rev.numero_revision:02d}"
        if rev.id == rev_actual.id:
            snap = _payload_para_diff(rev, doc, curr_payload)
        else:
            snap = _contenido_from_revision(rev, doc)

        descripcion = _diff_descripcion_cambios(
            prev_snapshot,
            snap,
            revision_label=rev.revision_label,
        )

        fecha_aprobacion = ""
        if rev.fecha_aprobacion:
            fecha_aprobacion = rev.fecha_aprobacion.isoformat()
        elif rev.id == rev_actual.id:
            fa = curr_payload.get("fecha_aprobacion")
            if fa:
                fecha_aprobacion = str(fa)[:10]

        rows.append(
            {
                "revision_ref": ref,
                "descripcion": descripcion[:4000],
                "fecha_aprobacion": fecha_aprobacion,
                "readonly": rev.id != rev_actual.id,
                "auto_generado": True,
            }
        )
        prev_snapshot = snap

    return rows


def default_contenido(titulo: str = "") -> dict[str, Any]:
    secciones = {key: "" for key, _ in PROCEDIMIENTO_SECCIONES}
    return {
        "titulo": titulo,
        "secciones": secciones,
        "control_cambios": [],
        "registros": [],
        "anexos": [],
    }


def next_codigo(tipo: str) -> str:
    prefix = f"QDV-{tipo.upper()}-"
    rows = db.session.scalars(
        select(SgiDocumento.codigo).where(
            SgiDocumento.tipo == tipo.upper(),
            SgiDocumento.codigo.ilike(f"{prefix}%"),
        )
    ).all()
    max_n = 0
    for cod in rows:
        m = _CODIGO_RE.match((cod or "").strip())
        if m and m.group(1).upper() == tipo.upper():
            max_n = max(max_n, int(m.group(2)))
    return f"{prefix}{max_n + 1:02d}"


def tipo_soporta_visual(tipo: str | None) -> bool:
    return (tipo or "").strip().upper() in TIPOS_PROCEDIMIENTO_VISUAL


def get_revision(rev_id: int) -> SgiProcedimientoRevision | None:
    return db.session.get(SgiProcedimientoRevision, int(rev_id))


def revision_actual(doc: SgiDocumento) -> SgiProcedimientoRevision | None:
    return doc.revisiones_proc.order_by(SgiProcedimientoRevision.numero_revision.desc()).first()


def revision_vigente_aprobada(doc: SgiDocumento) -> SgiProcedimientoRevision | None:
    return (
        doc.revisiones_proc.filter(
            SgiProcedimientoRevision.estado.in_((ESTADO_APROBADO, ESTADO_VIGENTE))
        )
        .order_by(SgiProcedimientoRevision.numero_revision.desc())
        .first()
    )


def revision_en_trabajo(doc: SgiDocumento) -> SgiProcedimientoRevision | None:
    return (
        doc.revisiones_proc.filter(
            SgiProcedimientoRevision.estado.in_((ESTADO_BORRADOR, ESTADO_EN_REVISION))
        )
        .order_by(SgiProcedimientoRevision.numero_revision.desc())
        .first()
    )


def puede_ver_documento(doc: SgiDocumento, *, puede_editar: bool) -> bool:
    if puede_editar:
        return True
    if doc.estado in (ESTADO_APROBADO, ESTADO_VIGENTE):
        return True
    if doc.es_procedimiento_visual:
        rev = revision_vigente_aprobada(doc)
        return rev is not None
    return doc.estado in (ESTADO_APROBADO, ESTADO_VIGENTE)


def estado_visual_row(doc: SgiDocumento) -> str:
    if doc.estado == ESTADO_BORRADOR:
        return "sgi-row-borrador"
    if doc.estado == ESTADO_EN_REVISION:
        return "sgi-row-revision"
    if doc.estado in (ESTADO_OBSOLETO,):
        return "sgi-row-obsoleto"
    if doc.estado in (ESTADO_APROBADO, ESTADO_VIGENTE):
        return "sgi-row-vigente"
    return "sgi-row-borrador"


def build_list_query_visual(
    args: dict[str, Any],
    *,
    tipo: str,
    incluir_obsoletos: bool = False,
    solo_obsoletos: bool = False,
) -> Select[Any]:
    q = select(SgiDocumento).where(
        SgiDocumento.tipo == tipo,
        SgiDocumento.es_procedimiento_visual.is_(True),
    )
    q_text = (args.get("q") or "").strip()
    estado = (args.get("estado") or "").strip()

    if solo_obsoletos:
        q = q.where(SgiDocumento.estado == ESTADO_OBSOLETO)
    elif not incluir_obsoletos:
        q = q.where(SgiDocumento.estado != ESTADO_OBSOLETO)

    if q_text:
        like = f"%{q_text}%"
        q = q.where(or_(SgiDocumento.codigo.ilike(like), SgiDocumento.titulo.ilike(like)))

    if estado:
        q = q.where(SgiDocumento.estado == estado)

    return q.order_by(SgiDocumento.codigo, SgiDocumento.id)


def fetch_list_visual(args: dict[str, Any], *, tipo: str, incluir_obsoletos: bool = False) -> list[SgiDocumento]:
    return list(db.session.scalars(build_list_query_visual(args, tipo=tipo, incluir_obsoletos=incluir_obsoletos)).all())


def _clear_dynamic(rel) -> None:
    for row in list(rel.all()):
        db.session.delete(row)


def _sync_child_rows(rev: SgiProcedimientoRevision, payload: dict[str, Any]) -> None:
    _clear_dynamic(rev.control_cambios)
    for i, row in enumerate(payload.get("control_cambios") or []):
        rev.control_cambios.append(
            SgiProcedimientoControlCambio(
                orden=i,
                revision_ref=(row.get("revision_ref") or "")[:32],
                descripcion=(row.get("descripcion") or "")[:4000],
                fecha_aprobacion=doc_svc.parse_iso_date(row.get("fecha_aprobacion")),
            )
        )

    _clear_dynamic(rev.registros)
    for i, row in enumerate(payload.get("registros") or []):
        rev.registros.append(
            SgiProcedimientoRegistro(
                orden=i,
                nombre=(row.get("nombre") or "").strip().upper()[:512],
                quien_archiva=(row.get("quien_archiva") or "")[:512],
                como=(row.get("como") or "")[:512],
                donde=(row.get("donde") or "")[:512],
                tiempo_guarda=(row.get("tiempo_guarda") or "")[:256],
                usuarios=(row.get("usuarios") or "")[:512],
                disposicion_final=(row.get("disposicion_final") or "")[:512],
            )
        )

    existing_anexos = {a.id: a for a in rev.anexos.all()}
    incoming = payload.get("anexos") or []
    seen_ids: set[int] = set()
    for i, row in enumerate(incoming):
        aid = row.get("id")
        if aid and int(aid) in existing_anexos:
            a = existing_anexos[int(aid)]
            seen_ids.add(a.id)
        else:
            a = SgiProcedimientoAnexo(revision_id=rev.id, orden=i)
            rev.anexos.append(a)
        a.orden = i
        a.nombre = (row.get("nombre") or "").strip().upper()[:512]
        a.codigo = (row.get("codigo") or "").strip().upper()[:64]
        a.revision = (row.get("revision") or "")[:32]
        a.fecha_vigencia = doc_svc.parse_iso_date(row.get("fecha_vigencia"))
        if not a.codigo and a.nombre:
            a.codigo = f"{rev.documento.codigo}-A{i + 1:02d}"

    for aid, a in existing_anexos.items():
        if aid not in seen_ids:
            db.session.delete(a)


def revision_to_payload(rev: SgiProcedimientoRevision) -> dict[str, Any]:
    try:
        base = json.loads(rev.contenido_json or "{}")
    except json.JSONDecodeError:
        base = default_contenido()
    if not isinstance(base, dict):
        base = default_contenido()

    base.setdefault("titulo", rev.documento.titulo if rev.documento else "")
    base.setdefault("secciones", {k: "" for k, _ in PROCEDIMIENTO_SECCIONES})
    base["secciones"] = normalize_procedure_secciones(base.get("secciones") or {})
    snap = {
        "titulo": base.get("titulo") or (rev.documento.titulo if rev.documento else ""),
        "secciones": base.get("secciones") or {},
        "registros": base.get("registros") or [],
        "anexos": base.get("anexos") or [],
        "fecha_aprobacion": base.get("fecha_aprobacion") or "",
    }
    if rev.documento:
        base["control_cambios"] = build_control_cambios_automatico(rev.documento, rev, snap)
    else:
        base["control_cambios"] = base.get("control_cambios") or []
    base["registros"] = [
        {
            "nombre": r.nombre,
            "quien_archiva": r.quien_archiva,
            "como": r.como,
            "donde": r.donde,
            "tiempo_guarda": r.tiempo_guarda,
            "usuarios": r.usuarios,
            "disposicion_final": r.disposicion_final,
        }
        for r in rev.registros.all()
    ]
    base["anexos"] = [
        {
            "id": a.id,
            "nombre": a.nombre,
            "codigo": a.codigo,
            "revision": a.revision,
            "fecha_vigencia": a.fecha_vigencia.isoformat() if a.fecha_vigencia else "",
            "tiene_archivo": bool(a.archivo_path),
        }
        for a in rev.anexos.all()
    ]
    return base


def create_procedimiento_visual(
    tipo: str,
    user_id: int,
    actor_label: str,
    *,
    titulo: str = "Título del procedimiento",
    actor: User | None = None,
) -> tuple[SgiDocumento | None, SgiProcedimientoRevision | None, str | None]:
    if not tipo_soporta_visual(tipo):
        return None, None, "Este tipo no admite el generador visual de procedimientos."

    titulo = (titulo or "").strip().upper() or "TÍTULO DEL PROCEDIMIENTO"
    codigo = next_codigo(tipo)
    contenido = default_contenido(titulo)
    doc = SgiDocumento(
        tipo=tipo.upper(),
        codigo=codigo,
        titulo=titulo[:512],
        revision="Rev. 00",
        estado=ESTADO_BORRADOR,
        es_procedimiento_visual=True,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.session.add(doc)
    db.session.flush()

    rev = SgiProcedimientoRevision(
        documento_id=doc.id,
        numero_revision=0,
        revision_label="Rev. 00",
        estado=ESTADO_BORRADOR,
        contenido_json=json.dumps(contenido, ensure_ascii=False),
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.session.add(rev)
    db.session.flush()
    contenido["control_cambios"] = build_control_cambios_automatico(doc, rev, contenido)
    rev.contenido_json = json.dumps(contenido, ensure_ascii=False)
    _sync_child_rows(rev, contenido)

    doc_svc.append_historial(doc.id, actor_label, doc_svc.ACCION_ALTA, f"Procedimiento visual {codigo}")
    db.session.commit()
    db.session.refresh(doc)
    db.session.refresh(rev)
    return doc, rev, None


def save_revision_content(
    rev_id: int,
    payload: dict[str, Any],
    user_id: int,
    actor_label: str,
    *,
    actor: User | None = None,
) -> tuple[bool, str, list[dict[str, Any]]]:
    rev = get_revision(rev_id)
    if rev is None:
        return False, "Revisión no encontrada.", []
    if rev.estado not in (ESTADO_BORRADOR, ESTADO_EN_REVISION):
        return False, "Solo se puede editar un borrador o documento en revisión.", []

    doc = rev.documento
    titulo = (payload.get("titulo") or doc.titulo or "").strip().upper()
    if len(titulo) < 2:
        return False, "El título debe tener al menos 2 caracteres.", []

    secciones = normalize_procedure_secciones(payload.get("secciones") or {})
    contenido = {
        "titulo": titulo,
        "secciones": secciones,
        "registros": payload.get("registros") or [],
        "anexos": payload.get("anexos") or [],
        "fecha_aprobacion": payload.get("fecha_aprobacion"),
    }
    contenido["control_cambios"] = build_control_cambios_automatico(doc, rev, contenido)
    rev.contenido_json = json.dumps(contenido, ensure_ascii=False)
    rev.fecha_vigencia = doc_svc.parse_iso_date(payload.get("fecha_vigencia"))
    rev.elaboro = (payload.get("elaboro") or "")[:256]
    rev.reviso = (payload.get("reviso") or "")[:256]
    rev.aprobo = (payload.get("aprobo") or "")[:256]
    rev.fecha_elaboracion = doc_svc.parse_iso_date(payload.get("fecha_elaboracion"))
    rev.fecha_revision = doc_svc.parse_iso_date(payload.get("fecha_revision"))
    rev.fecha_aprobacion = doc_svc.parse_iso_date(payload.get("fecha_aprobacion"))
    rev.updated_at = _utc_now()
    rev.updated_by_id = user_id

    doc.titulo = titulo[:512]
    doc.revision = rev.revision_label
    doc.responsable_elaboracion = rev.elaboro
    doc.responsable_revision = rev.reviso
    doc.responsable_aprobacion = rev.aprobo
    doc.fecha_ultima_revision = rev.fecha_vigencia
    doc.updated_at = _utc_now()
    doc.updated_by_id = user_id

    _sync_child_rows(rev, contenido)
    doc_svc.append_historial(doc.id, actor_label, doc_svc.ACCION_EDICION, f"Guardado {rev.revision_label}")
    db.session.commit()
    return True, "Borrador guardado.", contenido.get("control_cambios") or []


def _log_aprobacion(rev: SgiProcedimientoRevision, accion: str, user_id: int, label: str, detalle: str) -> None:
    db.session.add(
        SgiProcedimientoAprobacion(
            revision_id=rev.id,
            accion=accion,
            usuario_id=user_id,
            usuario_label=label[:256],
            detalle=detalle[:4000],
        )
    )


def enviar_a_revision(rev_id: int, user_id: int, actor_label: str) -> tuple[bool, str]:
    rev = get_revision(rev_id)
    if rev is None or rev.estado != ESTADO_BORRADOR:
        return False, "Solo un borrador puede enviarse a revisión."
    rev.estado = ESTADO_EN_REVISION
    rev.updated_by_id = user_id
    doc = rev.documento
    doc.estado = ESTADO_EN_REVISION
    doc.updated_by_id = user_id
    _log_aprobacion(rev, ACCION_ENVIAR_REVISION, user_id, actor_label, "Enviado a revisión")
    doc_svc.append_historial(doc.id, actor_label, doc_svc.ACCION_CAMBIO_ESTADO, "Borrador → En revisión")
    db.session.commit()
    return True, "Documento enviado a revisión."


def aprobar_revision(rev_id: int, user_id: int, actor_label: str) -> tuple[bool, str]:
    rev = get_revision(rev_id)
    if rev is None or rev.estado != ESTADO_EN_REVISION:
        return False, "Solo un documento en revisión puede aprobarse."
    doc = rev.documento
    hoy = date.today()

    previas = (
        doc.revisiones_proc.filter(
            SgiProcedimientoRevision.id != rev.id,
            SgiProcedimientoRevision.estado.in_((ESTADO_APROBADO, ESTADO_VIGENTE)),
        ).all()
    )
    for p in previas:
        p.estado = ESTADO_OBSOLETO
        _log_aprobacion(p, ACCION_APROBAR, user_id, actor_label, "Obsoleto por nueva aprobación")

    rev.estado = ESTADO_APROBADO
    rev.fecha_aprobacion = rev.fecha_aprobacion or hoy
    rev.aprobo = rev.aprobo or actor_label
    rev.updated_by_id = user_id

    doc.estado = ESTADO_APROBADO
    doc.fecha_aprobacion = rev.fecha_aprobacion
    doc.fecha_ultima_revision = rev.fecha_vigencia or rev.fecha_aprobacion
    doc.responsable_aprobacion = rev.aprobo
    doc.updated_by_id = user_id

    _log_aprobacion(rev, ACCION_APROBAR, user_id, actor_label, "Documento aprobado")

    try:
        data = json.loads(rev.contenido_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["fecha_aprobacion"] = rev.fecha_aprobacion.isoformat() if rev.fecha_aprobacion else ""
    data["control_cambios"] = build_control_cambios_automatico(doc, rev, data)
    rev.contenido_json = json.dumps(data, ensure_ascii=False)
    _sync_child_rows(rev, data)

    doc_svc.append_historial(doc.id, actor_label, doc_svc.ACCION_CAMBIO_ESTADO, f"Aprobado {rev.revision_label}")
    db.session.commit()
    return True, "Documento aprobado."


def crear_nueva_revision(doc_id: int, user_id: int, actor_label: str) -> tuple[SgiProcedimientoRevision | None, str | None]:
    doc = doc_svc.get_documento(doc_id)
    if doc is None or not doc.es_procedimiento_visual:
        return None, "Procedimiento no encontrado."
    if revision_en_trabajo(doc):
        return None, "Ya existe una revisión en borrador o en revisión."

    ultima = revision_actual(doc)
    num = (ultima.numero_revision + 1) if ultima else 0
    label = _revision_label(num)

    base_payload = revision_to_payload(ultima) if ultima else default_contenido(doc.titulo)

    rev = SgiProcedimientoRevision(
        documento_id=doc.id,
        numero_revision=num,
        revision_label=label,
        estado=ESTADO_BORRADOR,
        contenido_json=json.dumps(base_payload, ensure_ascii=False),
        elaboro=ultima.elaboro if ultima else "",
        reviso=ultima.reviso if ultima else "",
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.session.add(rev)
    db.session.flush()
    base_payload["control_cambios"] = build_control_cambios_automatico(doc, rev, base_payload)
    rev.contenido_json = json.dumps(base_payload, ensure_ascii=False)
    _sync_child_rows(rev, base_payload)

    doc.estado = ESTADO_BORRADOR
    doc.revision = label
    doc.updated_by_id = user_id
    _log_aprobacion(rev, ACCION_NUEVA_REVISION, user_id, actor_label, f"Nueva {label}")
    doc_svc.append_historial(doc.id, actor_label, doc_svc.ACCION_EDICION, f"Nueva revisión {label}")
    db.session.commit()
    db.session.refresh(rev)
    return rev, None


def historial_revisiones(doc_id: int) -> list[SgiProcedimientoRevision]:
    return list(
        db.session.scalars(
            select(SgiProcedimientoRevision)
            .where(SgiProcedimientoRevision.documento_id == int(doc_id))
            .order_by(SgiProcedimientoRevision.numero_revision.desc())
        ).all()
    )


def historial_aprobaciones(rev_id: int) -> list[SgiProcedimientoAprobacion]:
    return list(
        db.session.scalars(
            select(SgiProcedimientoAprobacion)
            .where(SgiProcedimientoAprobacion.revision_id == int(rev_id))
            .order_by(SgiProcedimientoAprobacion.fecha.desc())
        ).all()
    )


def save_anexo_file(
    anexo_id: int,
    storage: FileStorage | None,
    user_id: int,
) -> tuple[bool, str]:
    anexo = db.session.get(SgiProcedimientoAnexo, int(anexo_id))
    if anexo is None:
        return False, "Anexo no encontrado."
    if not storage or not (storage.filename or "").strip():
        return False, "No se seleccionó archivo."

    fn = secure_filename(storage.filename or "anexo")
    if not fn:
        return False, "Nombre inválido."
    if "." in fn:
        stem, _, ext = fn.rpartition(".")
        fn = f"{stem.upper()}.{ext.lower()}"
    else:
        fn = fn.upper()
    data = storage.read()
    if len(data) > doc_svc._upload_max_bytes():
        return False, "Archivo demasiado grande."

    rev = anexo.proc_revision
    base = uploads_workspace_root() / "sgi" / "procedimientos" / str(rev.documento_id) / str(rev.id) / "anexos"
    base.mkdir(parents=True, exist_ok=True)
    dest = base / fn
    dest.write_bytes(data)
    anexo.archivo_path = (Path("sgi") / "procedimientos" / str(rev.documento_id) / str(rev.id) / "anexos" / fn).as_posix()
    db.session.commit()
    return True, "Archivo de anexo guardado."


def anexo_absolute_path(rel: str | None) -> Path | None:
    return doc_svc.attachment_absolute_path(rel)
