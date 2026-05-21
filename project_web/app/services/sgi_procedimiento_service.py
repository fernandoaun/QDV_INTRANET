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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _revision_label(num: int) -> str:
    return f"Rev. {num:02d}"


def _parse_revision_num(label: str) -> int:
    m = re.search(r"(\d+)", label or "")
    if m:
        return int(m.group(1))
    return 0


def default_contenido(titulo: str = "") -> dict[str, Any]:
    secciones = {key: "" for key, _ in PROCEDIMIENTO_SECCIONES}
    return {
        "titulo": titulo,
        "secciones": secciones,
        "control_cambios": [{"revision_ref": "00", "descripcion": "Emisión inicial del documento.", "fecha_aprobacion": ""}],
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
                nombre=(row.get("nombre") or "")[:512],
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
        a.nombre = (row.get("nombre") or "")[:512]
        a.codigo = (row.get("codigo") or "")[:64]
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
    base["control_cambios"] = [
        {
            "revision_ref": c.revision_ref,
            "descripcion": c.descripcion,
            "fecha_aprobacion": c.fecha_aprobacion.isoformat() if c.fecha_aprobacion else "",
        }
        for c in rev.control_cambios.all()
    ] or base.get("control_cambios") or []
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
    titulo: str = "Nuevo procedimiento",
    actor: User | None = None,
) -> tuple[SgiDocumento | None, SgiProcedimientoRevision | None, str | None]:
    if not tipo_soporta_visual(tipo):
        return None, None, "Este tipo no admite el generador visual de procedimientos."

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
) -> tuple[bool, str]:
    rev = get_revision(rev_id)
    if rev is None:
        return False, "Revisión no encontrada."
    if rev.estado not in (ESTADO_BORRADOR, ESTADO_EN_REVISION):
        return False, "Solo se puede editar un borrador o documento en revisión."

    doc = rev.documento
    titulo = (payload.get("titulo") or doc.titulo or "").strip()
    if len(titulo) < 2:
        return False, "El título debe tener al menos 2 caracteres."

    secciones = payload.get("secciones") or {}
    contenido = {
        "titulo": titulo,
        "secciones": {k: (secciones.get(k) or "") for k, _ in PROCEDIMIENTO_SECCIONES},
        "control_cambios": payload.get("control_cambios") or [],
        "registros": payload.get("registros") or [],
        "anexos": payload.get("anexos") or [],
    }
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
    return True, "Borrador guardado."


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
    base_payload["control_cambios"].append(
        {"revision_ref": f"{num:02d}", "descripcion": "", "fecha_aprobacion": ""}
    )

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
