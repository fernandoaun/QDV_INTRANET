from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import current_app
from sqlalchemy import inspect, or_, select, text
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.archivo import KIND_REGISTRO, ArchivoCarga, ArchivoSubmodulo
from app.models.sgi import (
    ESTADO_OBSOLETO,
    TIPO_PG,
    TIPO_PO,
    SgiDocumento,
    SgiProcedimientoRegistro,
    SgiProcedimientoRevision,
)
from app.models.user import User
from app.services import sgi_procedimiento_service as proc_svc
from app.services.upload_paths import resolve_under_upload_roots, uploads_workspace_root

ALLOWED_EXT = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".odt",
        ".ods",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".tif",
        ".tiff",
    }
)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_SGI_BUCKET_CODE = "__sgi__"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def registro_clave(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", nombre or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s[:256]


def ensure_schema() -> None:
    """Completa columnas nuevas en SQLite local si Alembic no corrió."""
    insp = inspect(db.engine)
    if "archivo_cargas" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("archivo_cargas")}
    stmts: list[str] = []
    if "sgi_documento_id" not in cols:
        stmts.append("ALTER TABLE archivo_cargas ADD COLUMN sgi_documento_id INTEGER")
    if "sgi_registro_id" not in cols:
        stmts.append("ALTER TABLE archivo_cargas ADD COLUMN sgi_registro_id INTEGER")
    if "registro_clave" not in cols:
        stmts.append("ALTER TABLE archivo_cargas ADD COLUMN registro_clave VARCHAR(256) DEFAULT ''")
    if not stmts:
        return
    with db.engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))


def _sgi_bucket() -> ArchivoSubmodulo:
    row = ArchivoSubmodulo.query.filter_by(codigo=_SGI_BUCKET_CODE).first()
    if row is None:
        row = ArchivoSubmodulo(
            kind=KIND_REGISTRO,
            nombre="SGC",
            codigo=_SGI_BUCKET_CODE,
            descripcion="Interno: cargas colgadas de registros del SGC.",
            activo=False,
        )
        db.session.add(row)
        db.session.flush()
    return row


def list_procedimientos() -> list[SgiDocumento]:
    q = (
        select(SgiDocumento)
        .where(
            SgiDocumento.es_procedimiento_visual.is_(True),
            SgiDocumento.tipo.in_((TIPO_PG, TIPO_PO)),
            SgiDocumento.deleted_at.is_(None),
            SgiDocumento.estado != ESTADO_OBSOLETO,
        )
        .order_by(SgiDocumento.tipo.asc(), SgiDocumento.codigo.asc(), SgiDocumento.titulo.asc())
    )
    return list(db.session.scalars(q).all())


def get_procedimiento(doc_id: int) -> SgiDocumento | None:
    doc = db.session.get(SgiDocumento, int(doc_id))
    if doc is None or doc.deleted_at is not None:
        return None
    if not doc.es_procedimiento_visual or doc.tipo not in (TIPO_PG, TIPO_PO):
        return None
    if doc.estado == ESTADO_OBSOLETO:
        return None
    return doc


def revision_archivo(doc: SgiDocumento) -> SgiProcedimientoRevision | None:
    return (
        proc_svc.revision_vigente_aprobada(doc)
        or proc_svc.revision_en_trabajo(doc)
        or proc_svc.revision_actual(doc)
    )


def list_registros(doc: SgiDocumento) -> list[SgiProcedimientoRegistro]:
    rev = revision_archivo(doc)
    if rev is None:
        return []
    rows = list(
        db.session.scalars(
            select(SgiProcedimientoRegistro)
            .where(SgiProcedimientoRegistro.revision_id == rev.id)
            .order_by(SgiProcedimientoRegistro.orden.asc(), SgiProcedimientoRegistro.id.asc())
        ).all()
    )
    return [r for r in rows if (r.nombre or "").strip()]


def get_registro(doc: SgiDocumento, registro_id: int) -> SgiProcedimientoRegistro | None:
    row = db.session.get(SgiProcedimientoRegistro, int(registro_id))
    if row is None or not (row.nombre or "").strip():
        return None
    rev = db.session.get(SgiProcedimientoRevision, row.revision_id)
    if rev is None or rev.documento_id != doc.id:
        return None
    return row


def count_cargas_registro(doc_id: int, clave: str) -> int:
    if not clave:
        return 0
    return (
        ArchivoCarga.query.filter(
            ArchivoCarga.deleted_at.is_(None),
            ArchivoCarga.sgi_documento_id == int(doc_id),
            ArchivoCarga.registro_clave == clave,
        ).count()
    )


def counts_hub() -> dict[str, int]:
    tree = hub_tree()
    n_proc = sum(len(sec["procedimientos"]) for sec in tree)
    n_reg = sum(len(it["registros"]) for sec in tree for it in sec["procedimientos"])
    n_cargas = ArchivoCarga.query.filter(
        ArchivoCarga.deleted_at.is_(None),
        ArchivoCarga.sgi_documento_id.isnot(None),
    ).count()
    return {"procedimientos": n_proc, "registros": n_reg, "cargas": n_cargas}


def hub_tree() -> list[dict]:
    """PG y PO con sus registros del SGC y las cargas hechas en este módulo."""
    procs = list_procedimientos()
    doc_ids = [int(d.id) for d in procs]
    cargas_all: list[ArchivoCarga] = []
    if doc_ids:
        cargas_all = (
            ArchivoCarga.query.filter(
                ArchivoCarga.deleted_at.is_(None),
                ArchivoCarga.sgi_documento_id.in_(doc_ids),
            )
            .order_by(ArchivoCarga.uploaded_at.desc())
            .all()
        )
    by_key: dict[tuple[int, str], list[ArchivoCarga]] = {}
    by_rid: dict[tuple[int, int], list[ArchivoCarga]] = {}
    for c in cargas_all:
        did = int(c.sgi_documento_id or 0)
        if c.registro_clave:
            by_key.setdefault((did, c.registro_clave), []).append(c)
        if c.sgi_registro_id:
            by_rid.setdefault((did, int(c.sgi_registro_id)), []).append(c)

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def _cargas_of(doc: SgiDocumento, registro: SgiProcedimientoRegistro) -> list[ArchivoCarga]:
        clave = registro_clave(registro.nombre)
        seen: set[int] = set()
        out: list[ArchivoCarga] = []
        for c in by_rid.get((doc.id, int(registro.id)), []) + by_key.get((doc.id, clave), []):
            if c.id in seen:
                continue
            seen.add(c.id)
            out.append(c)
        out.sort(key=lambda x: x.uploaded_at or epoch, reverse=True)
        return out

    grouped: dict[str, list[dict]] = {TIPO_PG: [], TIPO_PO: []}
    for doc in procs:
        regs = []
        for r in list_registros(doc):
            cs = _cargas_of(doc, r)
            regs.append({"row": r, "n_cargas": len(cs), "cargas": cs})
        grouped.setdefault(doc.tipo, []).append({"doc": doc, "registros": regs})

    titles = {
        TIPO_PG: "Procedimientos de gestión",
        TIPO_PO: "Procedimientos operativos",
    }
    return [
        {"tipo": t, "title": titles[t], "procedimientos": grouped.get(t, [])}
        for t in (TIPO_PG, TIPO_PO)
    ]


def list_cargas_registro(doc: SgiDocumento, registro: SgiProcedimientoRegistro) -> list[ArchivoCarga]:
    clave = registro_clave(registro.nombre)
    return (
        ArchivoCarga.query.filter(
            ArchivoCarga.deleted_at.is_(None),
            ArchivoCarga.sgi_documento_id == int(doc.id),
            or_(
                ArchivoCarga.registro_clave == clave,
                ArchivoCarga.sgi_registro_id == int(registro.id),
            ),
        )
        .order_by(ArchivoCarga.uploaded_at.desc())
        .all()
    )


def get_carga(carga_id: int) -> ArchivoCarga | None:
    row = db.session.get(ArchivoCarga, carga_id)
    if row is None or row.deleted_at is not None:
        return None
    return row


def _parse_date(raw: str | None) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    return date.fromisoformat(s)


def save_carga_registro(
    doc: SgiDocumento,
    registro: SgiProcedimientoRegistro,
    fs: FileStorage | None,
    *,
    titulo: str = "",
    fecha_documento: str | None = None,
    notas: str = "",
    user: User | None = None,
) -> ArchivoCarga:
    if fs is None or not fs.filename:
        raise ValueError("Elegí un archivo para subir.")
    safe = secure_filename(fs.filename)
    if not safe:
        raise ValueError("El nombre del archivo no es válido.")
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("Tipo no permitido. Usá PDF, Word, Excel o imagen (PNG/JPEG/WebP/TIFF).")

    try:
        max_bytes = int(current_app.config.get("ARCHIVO_UPLOAD_MAX_BYTES") or MAX_UPLOAD_BYTES)
    except (TypeError, ValueError):
        max_bytes = MAX_UPLOAD_BYTES
    if max_bytes <= 0:
        max_bytes = MAX_UPLOAD_BYTES

    fs.seek(0)
    blob = fs.read(max_bytes + 1)
    if len(blob) > max_bytes:
        raise ValueError("El archivo supera el tamaño máximo permitido (20 MB).")

    try:
        fecha = _parse_date(fecha_documento)
    except ValueError as exc:
        raise ValueError("Fecha del documento inválida.") from exc

    bucket = _sgi_bucket()
    rel_dir = Path("archivo") / "sgi" / str(doc.id) / str(registro.id)
    target_dir = uploads_workspace_root() / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{ext}"
    rel_path = rel_dir / stored_name
    dest = target_dir / stored_name
    dest.write_bytes(blob)

    titulo_f = (titulo or "").strip() or Path(fs.filename).stem
    row = ArchivoCarga(
        submodulo_id=int(bucket.id),
        sgi_documento_id=int(doc.id),
        sgi_registro_id=int(registro.id),
        registro_clave=registro_clave(registro.nombre),
        titulo=titulo_f[:256],
        fecha_documento=fecha,
        notas=(notas or "").strip()[:2000],
        original_filename=(fs.filename or safe)[:256],
        stored_path=rel_path.as_posix(),
        mime_type=(fs.mimetype or "")[:128],
        size_bytes=len(blob),
        uploaded_by_id=int(user.id) if user is not None else None,
    )
    db.session.add(row)
    db.session.commit()
    return row


def resolve_carga_path(carga: ArchivoCarga) -> Path | None:
    return resolve_under_upload_roots(Path(carga.stored_path))


def soft_delete_carga(carga: ArchivoCarga) -> None:
    carga.deleted_at = _utc_now()
    db.session.commit()
