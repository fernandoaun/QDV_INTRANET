"""Generador visual de procedimientos SGI (PG / PO / MSGI)."""
from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import Select, func, or_, select
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.sgi import (
    ANEXO_TIPO_ARCHIVO,
    ANEXO_TIPO_DOCUMENTO,
    ANEXO_TIPO_ORGANIGRAMA,
    ESTADO_APROBADO,
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADO_OBSOLETO,
    ESTADO_REVISADO,
    ESTADO_VIGENTE,
    PROCEDIMIENTO_SECCIONES,
    SgiDocumento,
    SgiDocumentoHistorial,
    SgiProcedimientoAnexo,
    SgiProcedimientoAprobacion,
    SgiProcedimientoControlCambio,
    SgiProcedimientoRegistro,
    SgiProcedimientoRevision,
    TIPO_MSGI,
    TIPO_PG,
    TIPO_PO,
    TIPO_SLUGS,
    TIPOS_PROCEDIMIENTO_VISUAL,
)
from app.models.user import User
from app.auth_utils import user_can_edit_sgi_documentos, user_display_name
from app.services import sgi_documento_perfil_service as perfil_svc
from app.services import sgi_notification_service as notif_svc
from app.services import sgi_service as doc_svc
from app.services import sgi_workflow_service as workflow_svc
from app.services.upload_paths import uploads_workspace_root

ACCION_BORRADOR = "guardar_borrador"
ACCION_ENVIAR_REVISION = "enviar_revision"
ACCION_MARCAR_REVISADO = "marcar_revisado"
ACCION_APROBAR = "aprobar"
ACCION_NUEVA_REVISION = "nueva_revision"

_CODIGO_RE = re.compile(r"^QDV-(PG|PO|MSGI)-(\d+)$", re.IGNORECASE)
_ROMAN_VALUES: tuple[tuple[int, str], ...] = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def int_to_roman(value: int) -> str:
    """Convierte 1..3999 a numeral romano (p. ej. anexos MSGI: I, II, III)."""
    if value < 1 or value > 3999:
        raise ValueError("El valor debe estar entre 1 y 3999.")
    n = value
    parts: list[str] = []
    for amount, symbol in _ROMAN_VALUES:
        while n >= amount:
            parts.append(symbol)
            n -= amount
    return "".join(parts)


def anexo_codigo_auto(tipo: str, orden: int, parent_codigo: str) -> str:
    """Codificación automática de anexos: MSGI → QDV-ANEXO I/II/…; PG/PO → QDV-PG-01-A01."""
    idx = int(orden) + 1
    if (tipo or "").upper() == TIPO_MSGI:
        return f"QDV-ANEXO {int_to_roman(idx)}"
    return f"{parent_codigo}-A{idx:02d}"
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
            SgiProcedimientoRevision.estado.in_(
                (ESTADO_BORRADOR, ESTADO_EN_REVISION, ESTADO_REVISADO)
            )
        )
        .order_by(SgiProcedimientoRevision.numero_revision.desc())
        .first()
    )


def _label_matches_user(label: str, user: User) -> bool:
    needle = (label or "").strip().lower()
    if not needle:
        return False
    for cand in (user_display_name(user), user.username, user.nombre_completo or ""):
        hay = (cand or "").strip().lower()
        if hay and (hay == needle or hay in needle or needle in hay):
            return True
    return False


def user_can_marcar_revisado(user: User | None, rev: SgiProcedimientoRevision) -> bool:
    if user is None or rev.estado != ESTADO_EN_REVISION:
        return False
    if user.is_admin or user_can_edit_sgi_documentos(user):
        return True
    return _label_matches_user(rev.reviso, user)


def user_can_aprobar_revision(user: User | None, rev: SgiProcedimientoRevision) -> bool:
    if user is None or rev.estado != ESTADO_REVISADO:
        return False
    if user.is_admin or user_can_edit_sgi_documentos(user):
        return True
    return _label_matches_user(rev.aprobo, user)


def user_participates_workflow(user: User | None, rev: SgiProcedimientoRevision) -> bool:
    if user is None:
        return False
    if rev.estado == ESTADO_EN_REVISION and user_can_marcar_revisado(user, rev):
        return True
    if rev.estado == ESTADO_REVISADO and user_can_aprobar_revision(user, rev):
        return True
    return False


def documento_accesible_por_perfil(user: User, doc: SgiDocumento) -> bool:
    if doc.estado not in (ESTADO_APROBADO, ESTADO_VIGENTE):
        return False
    return perfil_svc.user_perfil_aplica_documento(user, doc.id)


def puede_ver_documento(doc: SgiDocumento, *, puede_editar: bool, user: User | None = None) -> bool:
    from app.auth_utils import user_can_access_sgi

    if puede_editar:
        return True
    if user and documento_accesible_por_perfil(user, doc):
        return True
    if user and user_can_access_sgi(user) and doc.estado in (ESTADO_APROBADO, ESTADO_VIGENTE):
        return True
    if doc.es_procedimiento_visual and user:
        rev_trabajo = revision_en_trabajo(doc)
        if rev_trabajo and user_participates_workflow(user, rev_trabajo):
            return True
        if doc.estado in (ESTADO_APROBADO, ESTADO_VIGENTE):
            return revision_vigente_aprobada(doc) is not None
    return False


def estado_visual_row(doc: SgiDocumento) -> str:
    if doc.estado == ESTADO_BORRADOR:
        return "sgi-row-borrador"
    if doc.estado in (ESTADO_EN_REVISION, ESTADO_REVISADO):
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


def ensure_revision_personas_mayusculas(rev: SgiProcedimientoRevision) -> bool:
    changed = False
    for attr in ("elaboro", "reviso", "aprobo"):
        if doc_svc._apply_upper_text_attr(rev, attr, max_len=256):
            changed = True
    return changed


def ensure_visual_documento_titulo_sync(doc: SgiDocumento) -> bool:
    """Alinea título y responsables en BD / revisión del procedimiento visual (mayúsculas)."""
    changed = doc_svc.ensure_documento_nombres_mayusculas(doc)
    rev = revision_en_trabajo(doc) or revision_vigente_aprobada(doc) or revision_actual(doc)
    if rev is None:
        return changed

    if ensure_revision_personas_mayusculas(rev):
        changed = True
    doc.responsable_elaboracion = rev.elaboro
    doc.responsable_revision = rev.reviso
    doc.responsable_aprobacion = rev.aprobo

    try:
        base = json.loads(rev.contenido_json or "{}")
    except json.JSONDecodeError:
        base = {}
    if not isinstance(base, dict):
        base = {}

    titulo_doc = (doc.titulo or "").strip()
    titulo_json = (base.get("titulo") or "").strip()
    titulo_upper = (titulo_doc or titulo_json).upper()
    if not titulo_upper:
        return changed

    if titulo_doc != titulo_upper:
        doc.titulo = titulo_upper[:512]
        changed = True
    if titulo_json != titulo_upper:
        base["titulo"] = titulo_upper
        rev.contenido_json = json.dumps(base, ensure_ascii=False)
        changed = True
    return changed


def ensure_list_visual_nombres_mayusculas(rows: list[SgiDocumento]) -> None:
    changed = any(ensure_visual_documento_titulo_sync(doc) for doc in rows)
    if changed:
        db.session.commit()


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
        if row.get("tipo_contenido"):
            from app.services import sgi_anexo_service as anexo_svc

            a.tipo_contenido = anexo_svc.normalize_tipo_contenido(row.get("tipo_contenido"))
        if not a.codigo and a.nombre and rev.documento:
            a.codigo = anexo_codigo_auto(rev.documento.tipo, i, rev.documento.codigo)

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
            "archivo_nombre": anexo_archivo_nombre(a.archivo_path),
            "vista_tipo": anexo_vista_tipo(a.archivo_path),
            "tipo_contenido": (a.tipo_contenido or ANEXO_TIPO_ARCHIVO),
        }
        for a in rev.anexos.all()
    ]
    if rev.documento:
        base["perfiles_aplica"] = perfil_svc.perfiles_aplica_documento(rev.documento_id)
    else:
        base["perfiles_aplica"] = []
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
    rev.elaboro = doc_svc.normalize_persona_campo(payload.get("elaboro"))[:256]
    rev.reviso = doc_svc.normalize_persona_campo(payload.get("reviso"))[:256]
    rev.revisor_correo = (payload.get("revisor_correo") or "").strip()[:256]
    rev.aprobo = doc_svc.normalize_persona_campo(payload.get("aprobo"))[:256]
    rev.aprobador_correo = (payload.get("aprobador_correo") or "")[:256]
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
    if "perfiles_aplica" in payload:
        perfil_svc.sync_perfiles_documento(doc.id, payload.get("perfiles_aplica"))
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
    doc = rev.documento
    if not (rev.reviso or "").strip():
        return False, "Indicá quién revisa (campo «Revisó» en la carátula) antes de enviar."
    if not perfil_svc.perfiles_aplica_documento(doc.id):
        return False, "Seleccioná al menos un sector/perfil al que aplica el procedimiento."
    rev.estado = ESTADO_EN_REVISION
    rev.updated_by_id = user_id
    doc.estado = ESTADO_EN_REVISION
    doc.updated_by_id = user_id
    _log_aprobacion(rev, ACCION_ENVIAR_REVISION, user_id, actor_label, "Enviado a revisión")
    doc_svc.append_historial(doc.id, actor_label, doc_svc.ACCION_CAMBIO_ESTADO, "Borrador → En revisión")
    db.session.commit()
    app = current_app._get_current_object()
    try:
        workflow_svc.notify_revision_requested(app, doc, rev)
    except Exception:
        current_app.logger.exception("SGI: fallo aviso correo a revisor rev_id=%s", rev_id)
    return True, "Documento enviado a revisión. Se notificó al revisor por correo."


def marcar_como_revisado(rev_id: int, user_id: int, actor_label: str) -> tuple[bool, str]:
    rev = get_revision(rev_id)
    if rev is None or rev.estado != ESTADO_EN_REVISION:
        return False, "Solo un documento en revisión puede marcarse como revisado."
    if not (rev.aprobo or "").strip():
        return False, "Indicá quién aprueba (campo «Aprobó» en la carátula) antes de continuar."
    hoy = date.today()
    rev.estado = ESTADO_REVISADO
    rev.fecha_revision = rev.fecha_revision or hoy
    rev.reviso = doc_svc.normalize_persona_campo(rev.reviso or actor_label)
    rev.updated_by_id = user_id
    doc = rev.documento
    doc.estado = ESTADO_REVISADO
    doc.responsable_revision = rev.reviso
    doc.updated_by_id = user_id
    _log_aprobacion(rev, ACCION_MARCAR_REVISADO, user_id, actor_label, "Marcado como revisado")
    doc_svc.append_historial(
        doc.id, actor_label, doc_svc.ACCION_CAMBIO_ESTADO, "En revisión → Revisado (pendiente aprobación)"
    )
    db.session.commit()
    app = current_app._get_current_object()
    try:
        workflow_svc.notify_pending_approval(app, doc, rev)
    except Exception:
        current_app.logger.exception("SGI: fallo aviso correo a aprobador rev_id=%s", rev_id)
    return True, "Revisión registrada. Se notificó al aprobador por correo."


def aprobar_revision(rev_id: int, user_id: int, actor_label: str) -> tuple[bool, str]:
    rev = get_revision(rev_id)
    if rev is None or rev.estado != ESTADO_REVISADO:
        return False, "Solo un documento revisado puede aprobarse."
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
    rev.aprobo = doc_svc.normalize_persona_campo(rev.aprobo or actor_label)
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
    try:
        n = notif_svc.create_approval_notifications(doc, rev, actor_label=actor_label)
    except Exception:
        current_app.logger.exception("SGI: fallo notificaciones in-app al aprobar rev_id=%s", rev_id)
        n = 0
    db.session.commit()
    if n > 0:
        return True, f"Documento aprobado. Se notificó a {n} usuario(s) de los sectores seleccionados."
    return True, "Documento aprobado. No hay usuarios activos en los sectores seleccionados para notificar."


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
        revisor_correo=ultima.revisor_correo if ultima else "",
        aprobo=ultima.aprobo if ultima else "",
        aprobador_correo=ultima.aprobador_correo if ultima else "",
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


def anexo_vista_tipo(archivo_path: str | None) -> str:
    """Tipo de presentación del adjunto: image, pdf, office o download."""
    if not archivo_path:
        return ""
    ext = Path(archivo_path).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".odt", ".odp"}:
        return "office"
    return "download"


def anexo_archivo_nombre(archivo_path: str | None) -> str:
    if not archivo_path:
        return ""
    return Path(archivo_path).name


def attach_anexo_file_from_path(anexo_id: int, source: Path) -> tuple[bool, str]:
    """Copia un archivo del disco al anexo (CLI / importación)."""
    src = Path(source)
    if not src.is_file():
        return False, f"Archivo no encontrado: {src}"
    anexo = db.session.get(SgiProcedimientoAnexo, int(anexo_id))
    if anexo is None:
        return False, "Anexo no encontrado."

    fn = secure_filename(src.name)
    if not fn:
        return False, "Nombre inválido."
    if "." in fn:
        stem, _, ext = fn.rpartition(".")
        fn = f"{stem.upper()}.{ext.lower()}"
    else:
        fn = fn.upper()
    data = src.read_bytes()
    if len(data) > doc_svc._upload_max_bytes():
        return False, "Archivo demasiado grande."

    rev = anexo.proc_revision
    base = uploads_workspace_root() / "sgi" / "procedimientos" / str(rev.documento_id) / str(rev.id) / "anexos"
    base.mkdir(parents=True, exist_ok=True)
    dest = base / fn
    shutil.copy2(src, dest)
    anexo.archivo_path = (Path("sgi") / "procedimientos" / str(rev.documento_id) / str(rev.id) / "anexos" / fn).as_posix()
    db.session.commit()
    return True, f"Archivo de anexo guardado: {fn}"


def attach_msgi_documento_file_from_path(doc_id: int, source: Path) -> tuple[bool, str]:
    """Copia un archivo fuente al documento MSGI independiente (p. ej. mapa de procesos)."""
    src = Path(source)
    if not src.is_file():
        return False, f"Archivo no encontrado: {src}"
    doc = db.session.get(SgiDocumento, int(doc_id))
    if doc is None:
        return False, "Documento no encontrado."

    fn = secure_filename(src.name)
    if not fn:
        return False, "Nombre inválido."
    if "." in fn:
        stem, _, ext = fn.rpartition(".")
        fn = f"{stem.upper()}.{ext.lower()}"
    else:
        fn = fn.upper()
    data = src.read_bytes()
    if len(data) > doc_svc._upload_max_bytes():
        return False, "Archivo demasiado grande."

    base = uploads_workspace_root() / "sgi" / str(doc.id)
    base.mkdir(parents=True, exist_ok=True)
    dest = base / fn
    shutil.copy2(src, dest)
    doc.archivo_path = (Path("sgi") / str(doc.id) / fn).as_posix()
    db.session.commit()
    return True, f"Archivo guardado: {fn}"


def _codigo_es_msgi_anexo_independiente(codigo: str) -> bool:
    return (codigo or "").strip().upper().startswith("QDV-ANEXO")


def create_msgi_documento_catalogo(
    *,
    codigo: str,
    titulo: str,
    tipo_contenido: str,
    revision_label: str,
    user_id: int,
    actor_label: str,
) -> tuple[SgiDocumento | None, SgiProcedimientoRevision | None, str | None]:
    """Crea un documento MSGI con código fijo (QDV-ANEXO I, II, …)."""
    from app.services import sgi_anexo_service as anexo_svc

    codigo = (codigo or "").strip().upper()
    titulo = (titulo or "").strip().upper() or codigo
    tipo = anexo_svc.normalize_tipo_contenido(tipo_contenido)
    if doc_svc._codigo_duplicado(TIPO_MSGI, codigo):
        return None, None, f"Ya existe un documento con código {codigo}."

    if tipo == ANEXO_TIPO_ORGANIGRAMA:
        contenido: dict[str, Any] = {"version": 1, "nodes": []}
    elif tipo == ANEXO_TIPO_DOCUMENTO:
        contenido = anexo_svc.default_documento_contenido(titulo)
    else:
        contenido = {}

    doc = SgiDocumento(
        tipo=TIPO_MSGI,
        codigo=codigo,
        titulo=titulo[:512],
        revision=revision_label or "Rev. 00",
        estado=ESTADO_BORRADOR,
        es_procedimiento_visual=True,
        tipo_contenido=tipo,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.session.add(doc)
    db.session.flush()

    rev = SgiProcedimientoRevision(
        documento_id=doc.id,
        numero_revision=0,
        revision_label=revision_label or "Rev. 00",
        estado=ESTADO_BORRADOR,
        contenido_json=json.dumps(contenido, ensure_ascii=False),
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.session.add(rev)
    db.session.flush()
    doc_svc.append_historial(doc.id, actor_label, doc_svc.ACCION_ALTA, f"Documento MSGI {codigo}")
    db.session.commit()
    db.session.refresh(doc)
    db.session.refresh(rev)
    return doc, rev, None


def _cleanup_msgi_anexos_embebidos_en_manuales(actor_label: str) -> list[str]:
    """Quita QDV-ANEXO I–IV de la sección 8 de manuales (son documentos aparte)."""
    logs: list[str] = []
    manuales = db.session.scalars(
        select(SgiDocumento).where(
            SgiDocumento.tipo == TIPO_MSGI,
            SgiDocumento.es_procedimiento_visual.is_(True),
            ~func.upper(SgiDocumento.codigo).like("QDV-ANEXO%"),
        )
    ).all()
    for manual in manuales:
        rev = revision_en_trabajo(manual) or revision_actual(manual)
        if rev is None:
            continue
        payload = revision_to_payload(rev)
        anexos = payload.get("anexos") or []
        filtrados = [
            a for a in anexos if not _codigo_es_msgi_anexo_independiente(str(a.get("codigo") or ""))
        ]
        if len(filtrados) == len(anexos):
            continue
        payload["anexos"] = filtrados
        base = json.loads(rev.contenido_json or "{}")
        rev.contenido_json = json.dumps({**base, "anexos": filtrados}, ensure_ascii=False)
        _sync_child_rows(rev, payload)
        doc_svc.append_historial(
            manual.id,
            actor_label,
            doc_svc.ACCION_EDICION,
            "Anexos I–IV retirados del manual (documentos independientes en MSGI).",
        )
        logs.append(f"{manual.codigo}: anexos I–IV quitados de la sección 8.")
    if logs:
        db.session.commit()
    return logs


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


def get_anexo_for_access(anexo_id: int, *, tipo_esperado: str | None = None) -> tuple[SgiProcedimientoAnexo | None, str | None]:
    """Devuelve anexo y mensaje de error si no existe o el tipo de documento no coincide."""
    anexo = db.session.get(SgiProcedimientoAnexo, int(anexo_id))
    if anexo is None or not anexo.archivo_path:
        return None, "Anexo no encontrado."
    rev = anexo.proc_revision
    doc = rev.documento if rev else None
    if doc is None:
        return None, "Documento no encontrado."
    if tipo_esperado and (doc.tipo or "").upper() != tipo_esperado.upper():
        return None, "Tipo de documento incorrecto."
    return anexo, None


def anexo_send_mimetype(path: Path) -> str:
    ext = path.suffix.lower()
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    return mapping.get(ext, "application/octet-stream")


FIRMA_GERENTE_DOC_STEM = "firma-gerente"
ALLOWED_FIRMA_GERENTE_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})


def _firma_gerente_doc_dir(doc_id: int) -> Path:
    return uploads_workspace_root() / "sgi" / "procedimientos" / str(int(doc_id))


def firma_gerente_relative_path(doc_id: int) -> str | None:
    base = _firma_gerente_doc_dir(doc_id)
    if not base.is_dir():
        return None
    for p in sorted(base.iterdir()):
        if p.is_file() and p.stem == FIRMA_GERENTE_DOC_STEM and p.suffix.lower() in ALLOWED_FIRMA_GERENTE_EXTENSIONS:
            return (Path("sgi") / "procedimientos" / str(int(doc_id)) / p.name).as_posix()
    return None


def global_firma_gerente_static_url() -> str | None:
    from flask import url_for

    static_root = Path(current_app.static_folder or "")
    for name in (
        "sgi-firma-gerente-general.png",
        "sgi-firma-gerente-general.jpg",
        "sgi-firma-gerente-general.jpeg",
        "sgi-firma-gerente-general.webp",
    ):
        if (static_root / "img" / name).is_file():
            return url_for("static", filename=f"img/{name}")
    return None


def firma_gerente_url_for_document(doc: SgiDocumento) -> str | None:
    from flask import url_for

    if (doc.tipo or "").upper() != TIPO_MSGI:
        return None
    if firma_gerente_relative_path(doc.id):
        slug = TIPO_SLUGS.get(TIPO_MSGI, "msgi")
        return url_for("sgi.firma_gerente", slug=slug, doc_id=doc.id)
    return global_firma_gerente_static_url()


def save_firma_gerente_file(
    doc_id: int,
    storage: FileStorage | None,
    user_id: int,
) -> tuple[bool, str]:
    doc = doc_svc.get_documento(doc_id)
    if doc is None:
        return False, "Documento no encontrado."
    if (doc.tipo or "").upper() != TIPO_MSGI:
        return False, "La firma del gerente general solo aplica a documentos MSGI."
    if not storage or not (storage.filename or "").strip():
        return False, "No se seleccionó imagen."

    fn = secure_filename(storage.filename or "firma")
    ext = Path(fn).suffix.lower()
    if ext not in ALLOWED_FIRMA_GERENTE_EXTENSIONS:
        return False, "Formato no permitido. Use PNG, JPG, WEBP o GIF."

    data = storage.read()
    if len(data) > doc_svc._upload_max_bytes():
        return False, "Imagen demasiado grande."

    base = _firma_gerente_doc_dir(doc.id)
    base.mkdir(parents=True, exist_ok=True)
    for old in base.iterdir():
        if old.is_file() and old.stem == FIRMA_GERENTE_DOC_STEM:
            try:
                old.unlink()
            except OSError:
                current_app.logger.warning("sgi: no se pudo borrar firma anterior %s", old)

    dest = base / f"{FIRMA_GERENTE_DOC_STEM}{ext}"
    dest.write_bytes(data)
    doc.updated_at = _utc_now()
    doc.updated_by_id = user_id
    db.session.commit()
    return True, "Firma del gerente general guardada."


def firma_gerente_absolute_path(doc_id: int) -> Path | None:
    rel = firma_gerente_relative_path(doc_id)
    if not rel:
        return None
    return doc_svc.attachment_absolute_path(rel)


def _msgi_anexos_data_dir() -> Path:
    configured = (current_app.config.get("SGI_MSGI_ANEXOS_DATA_DIR") or "").strip()
    if configured:
        return Path(configured)
    # root_path apunta a project_web/app; los archivos están en project_web/data/…
    return Path(current_app.root_path).parent / "data" / "sgi" / "msgi-anexos"


def default_msgi_anexo_catalog() -> tuple[dict[str, Any], ...]:
    """Catálogo de documentos MSGI independientes (QDV-ANEXO I–IV)."""
    data_dir = _msgi_anexos_data_dir()
    manual_dir = Path(
        current_app.config.get("SGI_MSGI_MANUAL_SOURCE_DIR")
        or r"c:\Users\ferna\OneDrive\Quimica del Valle\SGI\Manual de gestion"
    )
    return (
        {
            "codigo": "QDV-ANEXO I",
            "nombre": "POLÍTICA CSSA",
            "revision": "Rev. 00",
            "fecha_vigencia": None,
            "tipo_contenido": "documento",
            "archivo": _first_existing_path(
                data_dir / "QDV-ANEXO I Politica CSSA_Rev.00.docx",
                manual_dir / "QDV-ANEXO I Politica CSSA_Rev.00.docx",
            ),
        },
        {
            "codigo": "QDV-ANEXO II",
            "nombre": "ORGANIGRAMA",
            "revision": "Rev. 00",
            "fecha_vigencia": None,
            "tipo_contenido": "organigrama",
            "archivo": _first_existing_path(
                data_dir / "QDV-ANEXO II Organigrama_Rev.00.pptx",
                manual_dir / "QDV-ANEXO II Organigrama_Rev.00.pptx",
            ),
        },
        {
            "codigo": "QDV-ANEXO III",
            "nombre": "MAPA DE PROCESOS",
            "revision": "Rev. 00",
            "fecha_vigencia": date(2026, 5, 12),
            "tipo_contenido": "archivo",
            "archivo": _first_existing_path(
                data_dir / "QDV-ANEXO III Mapa de Procesos.png",
                manual_dir / "QDV-ANEXO III Mapa de Procesos.png",
            ),
        },
        {
            "codigo": "QDV-ANEXO IV",
            "nombre": "ANÁLISIS FODA",
            "revision": "Rev. 00",
            "fecha_vigencia": None,
            "tipo_contenido": "documento",
            "archivo": _first_existing_path(
                data_dir / "QDV-ANEXO IV Analisis FODA_Rev.00.docx",
                manual_dir / "QDV-ANEXO IV Analisis FODA_Rev.00.docx",
            ),
        },
    )


def _first_existing_path(*candidates: Path) -> Path | None:
    for path in candidates:
        if path is not None and Path(path).is_file():
            return Path(path)
    return None


def ensure_msgi_documentos(
    *,
    user_id: int | None = None,
    actor_label: str = "Sistema",
    catalog: tuple[dict[str, Any], ...] | None = None,
    refresh_organigrama: bool = False,
) -> tuple[list[SgiDocumento], list[str]]:
    """Registra QDV-ANEXO I–IV como documentos MSGI independientes (no anexos de un manual)."""
    from app.services import sgi_anexo_service as anexo_svc

    items = catalog or default_msgi_anexo_catalog()
    logs: list[str] = []
    docs: list[SgiDocumento] = []
    uid = user_id or 0

    for row in items:
        codigo = str(row.get("codigo") or "").strip().upper()
        if not codigo:
            continue
        nombre = (row.get("nombre") or codigo).strip().upper()
        rev_label = str(row.get("revision") or "Rev. 00").strip() or "Rev. 00"
        tipo = row.get("tipo_contenido") or ANEXO_TIPO_ARCHIVO

        doc = db.session.scalar(
            select(SgiDocumento).where(
                SgiDocumento.tipo == TIPO_MSGI,
                func.lower(SgiDocumento.codigo) == codigo.lower(),
            )
        )
        if doc is None:
            doc, rev, err = create_msgi_documento_catalogo(
                codigo=codigo,
                titulo=nombre,
                tipo_contenido=tipo,
                revision_label=rev_label,
                user_id=uid,
                actor_label=actor_label,
            )
            if doc is None:
                logs.append(f"{codigo}: {err or 'no se pudo crear.'}")
                continue
        else:
            doc.titulo = nombre[:512]
            doc.revision = rev_label
            doc.es_procedimiento_visual = True
            doc.tipo_contenido = anexo_svc.normalize_tipo_contenido(tipo)
            rev = revision_en_trabajo(doc) or revision_actual(doc)
            if rev is None:
                logs.append(f"{codigo}: sin revisión activa.")
                continue

        docs.append(doc)
        rev = revision_en_trabajo(doc) or revision_actual(doc)
        if rev is None:
            continue

        src = row.get("archivo")
        docx_src = Path(src) if src and str(src).lower().endswith((".docx", ".doc")) else None
        pptx_src = Path(src) if src and str(src).lower().endswith((".pptx", ".ppt")) else None
        anexo_svc.ensure_documento_tipo_contenido(
            doc,
            rev,
            tipo,
            docx_path=docx_src,
            pptx_path=pptx_src if tipo == ANEXO_TIPO_ORGANIGRAMA else None,
            refresh_organigrama=refresh_organigrama and (tipo == ANEXO_TIPO_ORGANIGRAMA),
        )
        db.session.flush()

        if tipo == ANEXO_TIPO_ORGANIGRAMA:
            logs.append(f"{codigo}: organigrama interactivo listo.")
        elif tipo == ANEXO_TIPO_DOCUMENTO:
            logs.append(f"{codigo}: documento visual importado.")
        if src and Path(src).is_file() and tipo == ANEXO_TIPO_ARCHIVO:
            if doc.archivo_path:
                logs.append(f"{codigo}: ya tenía archivo adjunto.")
            else:
                try:
                    ok, msg = attach_msgi_documento_file_from_path(doc.id, Path(src))
                    logs.append(f"{codigo}: {msg}" if ok else f"{codigo}: error — {msg}")
                except OSError as exc:
                    logs.append(f"{codigo}: error al leer archivo — {exc}")
        elif tipo == ANEXO_TIPO_ARCHIVO and not (src and Path(src).is_file()):
            logs.append(f"{codigo}: sin archivo fuente ({src or 'no configurado'}).")

    logs.extend(_cleanup_msgi_anexos_embebidos_en_manuales(actor_label))
    db.session.commit()
    return docs, logs


def ensure_msgi_manual_anexos(
    *,
    user_id: int | None = None,
    actor_label: str = "Sistema",
    catalog: tuple[dict[str, Any], ...] | None = None,
    doc_codigo: str | None = None,
    refresh_organigrama: bool = False,
) -> tuple[SgiDocumento | None, list[str]]:
    """Compatibilidad CLI: delega en documentos MSGI independientes."""
    del doc_codigo
    docs, logs = ensure_msgi_documentos(
        user_id=user_id,
        actor_label=actor_label,
        catalog=catalog,
        refresh_organigrama=refresh_organigrama,
    )
    return (docs[0] if docs else None), logs
