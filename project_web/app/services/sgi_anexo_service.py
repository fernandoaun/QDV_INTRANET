"""Anexos MSGI: documentos visuales (Word) y organigrama interactivo."""
from __future__ import annotations

import html
import json
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy import select

from app.extensions import db
from app.models.personal import EmpleadoPersonal
from app.models.sgi import (
    ANEXO_TIPO_ARCHIVO,
    ANEXO_TIPO_DOCUMENTO,
    ANEXO_TIPO_ORGANIGRAMA,
    PROCEDIMIENTO_SECCIONES,
    SgiProcedimientoAnexo,
)
from app.models.user import User
from app.services import sgi_procedimiento_service as proc_svc
from app.user_roles import ROLE_LABELS, normalize_stored_rol, role_label

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_TAG = f"{{{_W_NS}}}"


def normalize_tipo_contenido(raw: str | None) -> str:
    v = (raw or "").strip().lower()
    if v in (ANEXO_TIPO_DOCUMENTO, ANEXO_TIPO_ORGANIGRAMA):
        return v
    return ANEXO_TIPO_ARCHIVO


def default_documento_contenido(titulo: str = "") -> dict[str, Any]:
    secciones = {key: "" for key, _ in PROCEDIMIENTO_SECCIONES}
    return {"titulo": (titulo or "").strip().upper(), "secciones": secciones}


def parse_anexo_contenido(anexo: SgiProcedimientoAnexo) -> dict[str, Any]:
    try:
        data = json.loads(anexo.contenido_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if anexo.tipo_contenido == ANEXO_TIPO_DOCUMENTO:
        base = default_documento_contenido(anexo.nombre)
        base["titulo"] = (data.get("titulo") or anexo.nombre or "").strip().upper()
        secs = data.get("secciones") if isinstance(data.get("secciones"), dict) else {}
        base["secciones"] = proc_svc.normalize_procedure_secciones(secs)
        return base
    if anexo.tipo_contenido == ANEXO_TIPO_ORGANIGRAMA:
        nodes = data.get("nodes")
        if not isinstance(nodes, list):
            nodes = []
        return {"version": int(data.get("version") or 1), "nodes": nodes}
    return data


def documento_payload_for_view(anexo: SgiProcedimientoAnexo) -> dict[str, Any]:
    data = parse_anexo_contenido(anexo)
    return {
        "titulo": data.get("titulo") or anexo.nombre,
        "secciones": data.get("secciones") or {},
        "control_cambios": [],
        "registros": [],
        "anexos": [],
    }


def _docx_to_html_stdlib(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    chunks: list[str] = []
    for p in root.iter(f"{_W_TAG}p"):
        texts: list[str] = []
        for t in p.iter(f"{_W_TAG}t"):
            if t.text:
                texts.append(t.text)
            if t.tail:
                texts.append(t.tail)
        line = "".join(texts).strip()
        if line:
            chunks.append(f"<p>{html.escape(line)}</p>")
    return "\n".join(chunks) if chunks else "<p></p>"


def docx_to_html(path: Path) -> str:
    try:
        import mammoth

        with path.open("rb") as fh:
            result = mammoth.convert_to_html(fh)
        body = (result.value or "").strip()
        if body:
            return body
    except Exception:
        pass
    return _docx_to_html_stdlib(path)


def contenido_from_docx(path: Path, titulo: str) -> dict[str, Any]:
    body = docx_to_html(path)
    data = default_documento_contenido(titulo)
    data["secciones"]["desarrollo"] = proc_svc.normalize_procedure_html(body)
    return data


def _first_user_for_rol(rol: str) -> int | None:
    u = db.session.scalar(
        select(User.id).where(User.activo.is_(True), User.rol == rol).order_by(User.id).limit(1)
    )
    return int(u) if u is not None else None


def _slug_id(text: str) -> str:
    import re

    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower())
    return s.strip("_")[:48] or "nodo"


# Estructura extraída de QDV-ANEXO II Organigrama_Rev.00.pptx (SmartArt)
ORGANIGRAMA_QDV_SPECS: tuple[dict[str, Any], ...] = (
    {"id": "gerencia_general", "titulo": "GERENCIA GENERAL", "parent_id": None, "orden": 0, "rol": None},
    {"id": "responsable_administracion", "titulo": "RESPONSABLE DE ADMINISTRACIÓN", "parent_id": "gerencia_general", "orden": 1, "rol": "administracion"},
    {"id": "asesoria_impositiva_legal", "titulo": "ASESORÍA IMPOSITIVA Y LEGAL", "parent_id": "responsable_administracion", "orden": 2, "rol": None, "subtitulo": "Servicios externos"},
    {"id": "responsable_rrhh", "titulo": "RESPONSABLE DE RRHH", "parent_id": "gerencia_general", "orden": 3, "rol": None},
    {"id": "asesoria_rrhh", "titulo": "ASESORÍA RRHH", "parent_id": "responsable_rrhh", "orden": 4, "rol": None, "subtitulo": "Servicios externos"},
    {"id": "responsable_logistica", "titulo": "RESPONSABLE DE LOGÍSTICA Y DISTRIBUCIÓN", "parent_id": "gerencia_general", "orden": 5, "rol": "logistica"},
    {"id": "choferes", "titulo": "CHOFERES", "parent_id": "responsable_logistica", "orden": 6, "rol": "logistica"},
    {"id": "responsable_planta", "titulo": "RESPONSABLE DE PLANTA", "parent_id": "gerencia_general", "orden": 7, "rol": "operaciones"},
    {"id": "responsable_control_calidad", "titulo": "RESPONSABLE DE CONTROL DE CALIDAD", "parent_id": "responsable_planta", "orden": 8, "rol": "laboratorista"},
    {"id": "responsable_turno", "titulo": "RESPONSABLE DE TURNO", "parent_id": "responsable_planta", "orden": 9, "rol": "operaciones"},
    {"id": "operarios_planta", "titulo": "OPERARIOS DE PLANTA", "parent_id": "responsable_turno", "orden": 10, "rol": "operaciones"},
    {"id": "responsable_mantenimiento", "titulo": "RESPONSABLE DE MANTENIMIENTO", "parent_id": "responsable_planta", "orden": 11, "rol": "mantenimiento"},
    {"id": "asesoria_legal_contable", "titulo": "ASESORÍA LEGAL / CONTABLE", "parent_id": "gerencia_general", "orden": 12, "rol": None, "subtitulo": "Servicios externos"},
    {"id": "asesoria_qhse", "titulo": "ASESORÍA QHSE", "parent_id": "gerencia_general", "orden": 13, "rol": "sgi", "subtitulo": "Calidad, seguridad y medio ambiente"},
    {"id": "servicios_externos", "titulo": "SERVICIOS EXTERNOS", "parent_id": "gerencia_general", "orden": 14, "rol": None},
)


def parse_organigrama_from_pptx(path: Path) -> list[dict[str, Any]] | None:
    """Intenta leer la jerarquía del organigrama desde el PPTX (SmartArt)."""
    import re
    import zipfile
    import xml.etree.ElementTree as ET

    if not path.is_file():
        return None
    ns = {"dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram", "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    try:
        with zipfile.ZipFile(path) as zf:
            if "ppt/diagrams/data1.xml" not in zf.namelist():
                return None
            root = ET.fromstring(zf.read("ppt/diagrams/data1.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError):
        return None

    pts: dict[str, str] = {}
    for pt in root.findall(".//dgm:pt", ns):
        mid = pt.attrib.get("modelId", "")
        texts = [t.text.strip() for t in pt.findall(".//a:t", ns) if t.text and t.text.strip()]
        if texts and pt.attrib.get("type") not in ("doc", "parTrans", "sibTrans"):
            label = " ".join(texts)
            label = label.replace("Administracin", "Administración").replace("distribucin", "distribución")
            label = label.replace("Asesora", "Asesoría").replace("RRHHH", "RRHH")
            pts[mid] = label.upper()

    children: dict[str, list[tuple[int, str]]] = {}
    for cx in root.findall(".//dgm:cxn", ns):
        if cx.attrib.get("type") == "presOf":
            continue
        src, dest = cx.attrib.get("srcId"), cx.attrib.get("destId")
        if src in pts and dest in pts:
            children.setdefault(src, []).append((int(cx.attrib.get("srcOrd", 0)), dest))

    gerencia_id = next((k for k, v in pts.items() if "GERENCIA" in v.upper()), None)
    if not gerencia_id:
        return None

    nodes: list[dict[str, Any]] = []
    orden = 0

    def walk(nid: str, parent_slug: str | None) -> None:
        nonlocal orden
        titulo = pts[nid]
        slug = _slug_id(titulo)
        nodes.append(
            {
                "id": slug,
                "titulo": titulo,
                "subtitulo": "",
                "parent_id": parent_slug,
                "user_id": None,
                "orden": orden,
            }
        )
        orden += 1
        for _, child_id in sorted(children.get(nid, []), key=lambda x: x[0]):
            walk(child_id, slug)

    walk(gerencia_id, None)
    # Servicios externos aparece en la lámina pero fuera del SmartArt
    if not any(n["id"] == "servicios_externos" for n in nodes):
        nodes.append(
            {
                "id": "servicios_externos",
                "titulo": "SERVICIOS EXTERNOS",
                "subtitulo": "",
                "parent_id": "gerencia_general",
                "user_id": None,
                "orden": orden,
            }
        )
    return nodes if len(nodes) >= 5 else None


def build_default_organigrama_nodes(
    *,
    preserve_users: dict[str, int] | None = None,
    pptx_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Árbol inicial QDV; conserva asignaciones de usuario por id de nodo."""
    parsed = parse_organigrama_from_pptx(pptx_path) if pptx_path else None
    specs = parsed if parsed else [dict(s) for s in ORGANIGRAMA_QDV_SPECS]
    preserve = preserve_users or {}
    admin_id = db.session.scalar(
        select(User.id).where(User.activo.is_(True), User.is_admin.is_(True)).order_by(User.id).limit(1)
    )
    rol_by_id = {s["id"]: s.get("rol") for s in ORGANIGRAMA_QDV_SPECS}

    nodes: list[dict[str, Any]] = []
    for i, spec in enumerate(specs):
        nid = spec.get("id") or _slug_id(spec.get("titulo", f"n{i}"))
        uid = preserve.get(nid)
        if uid is None and nid == "gerencia_general" and admin_id:
            uid = int(admin_id)
        if uid is None:
            rol = rol_by_id.get(nid) or spec.get("rol")
            if rol:
                uid = _first_user_for_rol(rol)
        nodes.append(
            {
                "id": nid,
                "titulo": (spec.get("titulo") or "").strip().upper()[:256],
                "subtitulo": (spec.get("subtitulo") or "")[:256],
                "parent_id": spec.get("parent_id"),
                "user_id": uid,
                "orden": int(spec.get("orden") if spec.get("orden") is not None else i),
            }
        )
    return nodes


def organigrama_tree(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for n in nodes:
        pid = n.get("parent_id") or None
        by_parent.setdefault(pid, []).append(n)
    for kids in by_parent.values():
        kids.sort(key=lambda x: int(x.get("orden") or 0))

    user_ids = {int(n["user_id"]) for n in nodes if n.get("user_id")}
    users: dict[int, User] = {}
    if user_ids:
        for u in db.session.scalars(select(User).where(User.id.in_(user_ids))).all():
            users[u.id] = u
    legajos: dict[int, EmpleadoPersonal] = {}
    if user_ids:
        for emp in db.session.scalars(select(EmpleadoPersonal).where(EmpleadoPersonal.user_id.in_(user_ids))).all():
            if emp.user_id:
                legajos[int(emp.user_id)] = emp

    def enrich(node: dict[str, Any]) -> dict[str, Any]:
        row = dict(node)
        uid = row.get("user_id")
        u = users.get(int(uid)) if uid else None
        emp = legajos.get(int(uid)) if uid else None
        if u is not None:
            row["usuario"] = {
                "id": u.id,
                "nombre": (u.nombre_completo or u.username or "").strip(),
                "username": u.username,
                "rol": role_label(u.rol),
                "rol_key": normalize_stored_rol(u.rol),
                "puesto": (emp.puesto if emp else "") or ROLE_LABELS.get(normalize_stored_rol(u.rol), ""),
                "area": (emp.area if emp else "") or "",
                "email": (emp.email if emp else "") or "",
                "telefono": (emp.telefono if emp else "") or "",
            }
        else:
            row["usuario"] = None
        row["children"] = [enrich(c) for c in by_parent.get(row.get("id"), [])]
        return row

    return [enrich(n) for n in by_parent.get(None, [])]


def organigrama_usuarios_opciones() -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(User).where(User.activo.is_(True)).order_by(User.nombre_completo, User.username)
    ).all()
    out: list[dict[str, Any]] = []
    for u in rows:
        emp = u.empleado_personal if hasattr(u, "empleado_personal") else None
        out.append(
            {
                "id": u.id,
                "label": (u.nombre_completo or u.username or "").strip(),
                "rol": role_label(u.rol),
                "puesto": (emp.puesto if emp else "") or "",
            }
        )
    return out


def save_anexo_contenido(anexo_id: int, payload: dict[str, Any]) -> tuple[bool, str]:
    anexo = db.session.get(SgiProcedimientoAnexo, int(anexo_id))
    if anexo is None:
        return False, "Anexo no encontrado."
    tipo = anexo.tipo_contenido
    if tipo == ANEXO_TIPO_DOCUMENTO:
        titulo = (payload.get("titulo") or anexo.nombre or "").strip().upper()
        secciones = proc_svc.normalize_procedure_secciones(payload.get("secciones") or {})
        data = {"titulo": titulo, "secciones": secciones}
        anexo.contenido_json = json.dumps(data, ensure_ascii=False)
        if titulo:
            anexo.nombre = titulo[:512]
    elif tipo == ANEXO_TIPO_ORGANIGRAMA:
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            return False, "Estructura de organigrama inválida."
        clean: list[dict[str, Any]] = []
        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                continue
            nid = (n.get("id") or f"n{i}").strip()[:64]
            if not nid:
                continue
            uid = n.get("user_id")
            clean.append(
                {
                    "id": nid,
                    "titulo": (n.get("titulo") or "").strip().upper()[:256],
                    "subtitulo": (n.get("subtitulo") or "").strip()[:256],
                    "parent_id": (n.get("parent_id") or None) or None,
                    "user_id": int(uid) if uid not in (None, "", 0) else None,
                    "orden": int(n.get("orden") if n.get("orden") is not None else i),
                }
            )
        anexo.contenido_json = json.dumps({"version": 1, "nodes": clean}, ensure_ascii=False)
    else:
        return False, "Este anexo no admite edición de contenido."
    db.session.commit()
    return True, "Contenido guardado."


def ensure_anexo_tipo_contenido(
    anexo: SgiProcedimientoAnexo,
    tipo: str,
    *,
    docx_path: Path | None = None,
    pptx_path: Path | None = None,
    refresh_organigrama: bool = False,
) -> None:
    anexo.tipo_contenido = normalize_tipo_contenido(tipo)
    if anexo.tipo_contenido == ANEXO_TIPO_DOCUMENTO:
        if not (anexo.contenido_json or "").strip() or anexo.contenido_json == "{}":
            if docx_path and docx_path.is_file():
                data = contenido_from_docx(docx_path, anexo.nombre)
            else:
                data = default_documento_contenido(anexo.nombre)
            anexo.contenido_json = json.dumps(data, ensure_ascii=False)
    elif anexo.tipo_contenido == ANEXO_TIPO_ORGANIGRAMA:
        empty = not (anexo.contenido_json or "").strip() or anexo.contenido_json == "{}"
        if empty or refresh_organigrama:
            preserve: dict[str, int] = {}
            if not empty:
                try:
                    prev = json.loads(anexo.contenido_json or "{}")
                    for n in prev.get("nodes") or []:
                        if isinstance(n, dict) and n.get("id") and n.get("user_id"):
                            preserve[str(n["id"])] = int(n["user_id"])
                except (json.JSONDecodeError, TypeError, ValueError):
                    preserve = {}
            nodes = build_default_organigrama_nodes(preserve_users=preserve, pptx_path=pptx_path)
            anexo.contenido_json = json.dumps({"version": 1, "nodes": nodes}, ensure_ascii=False)
