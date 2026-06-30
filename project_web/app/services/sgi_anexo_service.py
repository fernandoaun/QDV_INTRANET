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
    SgiDocumento,
    SgiProcedimientoAnexo,
    SgiProcedimientoRevision,
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

# Posición en grilla (como QDV-ANEXO II / lámina de referencia)
ORGANIGRAMA_QDV_GRID: tuple[dict[str, Any], ...] = (
    {"id": "gerencia_general", "row": 1, "col": 7, "kind": "internal"},
    {"id": "asesoria_legal_contable", "row": 2, "col": 12, "kind": "external"},
    {"id": "responsable_administracion", "row": 3, "col": 2, "kind": "internal"},
    {"id": "responsable_rrhh", "row": 3, "col": 4, "kind": "internal"},
    {"id": "responsable_logistica", "row": 3, "col": 6, "kind": "internal"},
    {"id": "responsable_planta", "row": 3, "col": 8, "kind": "internal"},
    {"id": "asesoria_qhse", "row": 3, "col": 12, "kind": "external"},
    {"id": "asesoria_impositiva_legal", "row": 4, "col": 2, "kind": "external"},
    {"id": "asesoria_rrhh", "row": 4, "col": 4, "kind": "external"},
    {"id": "choferes", "row": 4, "col": 6, "kind": "internal"},
    {"id": "responsable_control_calidad", "row": 4, "col": 7, "kind": "internal"},
    {"id": "responsable_turno", "row": 4, "col": 8, "kind": "internal"},
    {"id": "responsable_mantenimiento", "row": 4, "col": 9, "kind": "internal"},
    {"id": "operarios_planta", "row": 5, "col": 8, "kind": "internal"},
)

ORGANIGRAMA_QDV_LINKS: tuple[dict[str, Any], ...] = (
    {"type": "bus", "from": "gerencia_general", "children": [
        "responsable_administracion",
        "responsable_rrhh",
        "responsable_logistica",
        "responsable_planta",
    ], "style": "solid"},
    {"type": "stem-side", "from": "gerencia_general", "to": "asesoria_legal_contable", "style": "dashed"},
    {"type": "bus-tail", "from": "gerencia_general", "to": "asesoria_qhse", "style": "dashed",
     "bus": "gerencia_internal"},
    {"type": "direct", "from": "responsable_administracion", "to": "asesoria_impositiva_legal", "style": "dashed"},
    {"type": "direct", "from": "responsable_rrhh", "to": "asesoria_rrhh", "style": "dashed"},
    {"type": "direct", "from": "responsable_logistica", "to": "choferes", "style": "solid"},
    {"type": "bus", "from": "responsable_planta", "children": [
        "responsable_control_calidad",
        "responsable_turno",
        "responsable_mantenimiento",
    ], "style": "solid"},
    {"type": "direct", "from": "responsable_turno", "to": "operarios_planta", "style": "solid"},
)


def _organigrama_node_user_ids(node: dict[str, Any]) -> list[int]:
    raw = node.get("user_ids")
    if isinstance(raw, list):
        out: list[int] = []
        for item in raw:
            try:
                uid = int(item)
            except (TypeError, ValueError):
                continue
            if uid > 0 and uid not in out:
                out.append(uid)
        if out:
            return out
    uid = node.get("user_id")
    if uid not in (None, "", 0):
        try:
            return [int(uid)]
        except (TypeError, ValueError):
            return []
    return []


def _organigrama_node_nivel(node_id: str, by_id: dict[str, dict[str, Any]], depth_cache: dict[str, int]) -> int:
    """Altura visual del recuadro: 0 = fila superior, 1 = siguiente, etc."""
    node = by_id.get(node_id)
    if not node:
        return 0
    raw = node.get("nivel")
    if raw is not None and raw != "":
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            pass
    depth = _organigrama_node_depth(node_id, by_id, depth_cache)
    return max(0, depth - 1)


def _organigrama_clean_node(n: dict[str, Any], index: int) -> dict[str, Any] | None:
    nid = (n.get("id") or f"n{index}").strip()[:64]
    if not nid:
        return None
    user_ids = _organigrama_node_user_ids(n)
    nivel: int | None = None
    raw_nivel = n.get("nivel")
    if raw_nivel is not None and raw_nivel != "":
        try:
            nivel = max(0, int(raw_nivel))
        except (TypeError, ValueError):
            nivel = None
    return {
        "id": nid,
        "titulo": (n.get("titulo") or "").strip().upper()[:256],
        "subtitulo": (n.get("subtitulo") or "").strip()[:256],
        "parent_id": (n.get("parent_id") or None) or None,
        "user_id": user_ids[0] if user_ids else None,
        "user_ids": user_ids,
        "orden": int(n.get("orden") if n.get("orden") is not None else index),
        "nivel": nivel,
        "kind": _organigrama_node_kind(n),
    }


def organigrama_nodes_for_editor(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            continue
        clean = _organigrama_clean_node(n, i)
        if clean:
            out.append(clean)
    if out:
        by_id = {str(n["id"]): n for n in out}
        depth_cache: dict[str, int] = {}
        for row in out:
            if row.get("nivel") is None:
                row["nivel"] = _organigrama_node_nivel(str(row["id"]), by_id, depth_cache)
    return out


def _organigrama_spec_by_id() -> dict[str, dict[str, Any]]:
    return {str(s["id"]): dict(s) for s in ORGANIGRAMA_QDV_SPECS}


def organigrama_ensure_complete_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Garantiza los 14 puestos de la grilla QDV; conserva usuarios asignados por id."""
    required = {str(s["id"]) for s in ORGANIGRAMA_QDV_GRID}
    by_id: dict[str, dict[str, Any]] = {}
    for n in nodes:
        if isinstance(n, dict) and n.get("id"):
            by_id[str(n["id"])] = n
    if required.issubset(by_id.keys()):
        specs = _organigrama_spec_by_id()
        ordered: list[dict[str, Any]] = []
        for gid in (s["id"] for s in ORGANIGRAMA_QDV_GRID):
            base = dict(specs.get(gid, {}))
            saved = by_id.get(gid, {})
            user_ids = _organigrama_node_user_ids(saved)
            merged = {
                "id": gid,
                "titulo": (saved.get("titulo") or base.get("titulo") or gid),
                "subtitulo": saved.get("subtitulo") or base.get("subtitulo") or "",
                "parent_id": saved.get("parent_id") if saved.get("parent_id") is not None else base.get("parent_id"),
                "user_id": user_ids[0] if user_ids else saved.get("user_id"),
                "user_ids": user_ids,
                "orden": saved.get("orden") if saved.get("orden") is not None else base.get("orden"),
                "nivel": saved.get("nivel") if saved.get("nivel") is not None else base.get("nivel"),
            }
            merged["kind"] = _organigrama_node_kind({**base, **saved, **merged})
            ordered.append(merged)
        return ordered
    preserve: dict[str, int] = {}
    for nid, n in by_id.items():
        if n.get("user_id"):
            preserve[nid] = int(n["user_id"])
    return build_default_organigrama_nodes(preserve_users=preserve, pptx_path=organigrama_pptx_path())


def organigrama_flat_nodes(arbol: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def walk(n: dict[str, Any]) -> None:
        out[str(n.get("id") or "")] = n
        for c in n.get("children") or []:
            if isinstance(c, dict):
                walk(c)

    for root in arbol:
        if isinstance(root, dict):
            walk(root)
    return out


def organigrama_layout_items(arbol: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compatibilidad: delega en el layout dinámico por niveles."""
    flat = organigrama_flat_nodes(arbol)
    nodes = [
        {
            "id": nid,
            "titulo": node.get("titulo") or nid,
            "subtitulo": node.get("subtitulo") or "",
            "parent_id": node.get("parent_id"),
            "orden": node.get("orden") or 0,
        }
        for nid, node in flat.items()
    ]
    levels = organigrama_chart_levels(nodes)
    items: list[dict[str, Any]] = []
    for level_idx, row in enumerate(levels, start=1):
        for col_idx, node in enumerate(row, start=1):
            items.append({**node, "row": level_idx, "col": col_idx})
    return items


ORGANIGRAMA_EXTERNAL_IDS: frozenset[str] = frozenset(
    {
        "asesoria_impositiva_legal",
        "asesoria_rrhh",
        "asesoria_legal_contable",
        "asesoria_qhse",
        "servicios_externos",
    }
)


def _organigrama_node_kind(node: dict[str, Any]) -> str:
    raw_kind = (node.get("kind") or "").strip().lower()
    if raw_kind in ("external", "externo"):
        return "external"
    if raw_kind in ("internal", "interno"):
        return "internal"
    nid = str(node.get("id") or "")
    if nid in ORGANIGRAMA_EXTERNAL_IDS:
        return "external"
    sub = (node.get("subtitulo") or "").lower()
    if "extern" in sub or "servicio" in sub:
        return "external"
    return "internal"


def _organigrama_node_depth(node_id: str, by_id: dict[str, dict[str, Any]], cache: dict[str, int], chain: set[str] | None = None) -> int:
    if node_id in cache:
        return cache[node_id]
    chain = chain or set()
    if node_id in chain:
        cache[node_id] = 1
        return 1
    chain.add(node_id)
    node = by_id.get(node_id)
    if not node:
        cache[node_id] = 1
        return 1
    parent_id = node.get("parent_id")
    if not parent_id or str(parent_id) not in by_id:
        cache[node_id] = 1
        return 1
    depth = _organigrama_node_depth(str(parent_id), by_id, cache, chain) + 1
    cache[node_id] = depth
    return depth


def organigrama_chart_levels(nodes: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Agrupa puestos por nivel jerárquico para dibujar el organigrama."""
    clean = [n for n in nodes if isinstance(n, dict) and n.get("id")]
    if not clean:
        return []
    by_id = {str(n["id"]): n for n in clean}
    arbol = organigrama_tree(clean)
    flat = organigrama_flat_nodes(arbol)
    depth_cache: dict[str, int] = {}
    by_level: dict[int, list[dict[str, Any]]] = {}
    for nid, base in by_id.items():
        enriched = flat.get(nid, {})
        level = _organigrama_node_nivel(nid, by_id, depth_cache)
        usuarios = enriched.get("usuarios") or []
        item = {
            "id": nid,
            "titulo": (enriched.get("titulo") or base.get("titulo") or nid),
            "subtitulo": enriched.get("subtitulo") or base.get("subtitulo") or "",
            "parent_id": base.get("parent_id"),
            "kind": _organigrama_node_kind({**base, **enriched}),
            "usuario": enriched.get("usuario"),
            "usuarios": usuarios,
            "level": level,
            "orden": int(base.get("orden") or 0),
        }
        by_level.setdefault(level, []).append(item)
    for lvl in by_level:
        by_level[lvl].sort(key=lambda x: (x["orden"], x["titulo"]))
    return [by_level[k] for k in sorted(by_level.keys())]


def organigrama_view_context(
    *,
    anexo: SgiProcedimientoAnexo | None = None,
    doc: SgiDocumento | None = None,
    rev: SgiProcedimientoRevision | None = None,
) -> dict[str, Any]:
    arbol = organigrama_view_arbol(anexo=anexo, doc=doc, rev=rev)
    if anexo is not None:
        data = parse_anexo_contenido(anexo)
    elif doc is not None and rev is not None:
        data = parse_documento_contenido(doc, rev)
    else:
        data = {}
    nodes = organigrama_ensure_complete_nodes(data.get("nodes") or [])
    chart_levels = organigrama_chart_levels(nodes)
    return {
        "arbol": arbol,
        "chart_levels": chart_levels,
        "layout_items": organigrama_layout_items(arbol),
    }


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
        node = {
            "id": nid,
            "titulo": (spec.get("titulo") or "").strip().upper()[:256],
            "subtitulo": (spec.get("subtitulo") or "")[:256],
            "parent_id": spec.get("parent_id"),
            "user_id": uid,
            "orden": int(spec.get("orden") if spec.get("orden") is not None else i),
        }
        node["kind"] = _organigrama_node_kind(node)
        nodes.append(node)
    return nodes


def organigrama_tree(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for n in nodes:
        pid = n.get("parent_id") or None
        by_parent.setdefault(pid, []).append(n)
    for kids in by_parent.values():
        kids.sort(key=lambda x: int(x.get("orden") or 0))

    user_ids: set[int] = set()
    for n in nodes:
        user_ids.update(_organigrama_node_user_ids(n))
    users: dict[int, User] = {}
    if user_ids:
        for u in db.session.scalars(select(User).where(User.id.in_(user_ids))).all():
            users[u.id] = u
    legajos: dict[int, EmpleadoPersonal] = {}
    if user_ids:
        for emp in db.session.scalars(select(EmpleadoPersonal).where(EmpleadoPersonal.user_id.in_(user_ids))).all():
            if emp.user_id:
                legajos[int(emp.user_id)] = emp

    def _usuario_payload(uid: int) -> dict[str, Any]:
        u = users.get(uid)
        if u is None:
            return {}
        emp = legajos.get(uid)
        return {
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

    def enrich(node: dict[str, Any]) -> dict[str, Any]:
        row = dict(node)
        node_user_ids = _organigrama_node_user_ids(row)
        row["user_ids"] = node_user_ids
        usuarios = []
        for uid in node_user_ids:
            payload = _usuario_payload(uid)
            if payload:
                usuarios.append(payload)
        row["usuarios"] = usuarios
        row["usuario"] = usuarios[0] if usuarios else None
        row["children"] = [enrich(c) for c in by_parent.get(row.get("id"), [])]
        return row

    return [enrich(n) for n in by_parent.get(None, [])]


def organigrama_pptx_path() -> Path | None:
    try:
        from flask import current_app

        from app.services.sgi_procedimiento_service import _first_existing_path, _msgi_anexos_data_dir

        data_dir = _msgi_anexos_data_dir()
        manual_dir = Path(
            current_app.config.get("SGI_MSGI_MANUAL_SOURCE_DIR")
            or r"c:\Users\ferna\OneDrive\Quimica del Valle\SGI\Manual de gestion"
        )
        return _first_existing_path(
            data_dir / "QDV-ANEXO II Organigrama_Rev.00.pptx",
            manual_dir / "QDV-ANEXO II Organigrama_Rev.00.pptx",
        )
    except Exception:
        return None


def organigrama_view_arbol(
    *,
    anexo: SgiProcedimientoAnexo | None = None,
    doc: SgiDocumento | None = None,
    rev: SgiProcedimientoRevision | None = None,
) -> list[dict[str, Any]]:
    """Árbol listo para la vista; si no hay nodos guardados, carga la estructura QDV por defecto."""
    if anexo is not None:
        data = parse_anexo_contenido(anexo)
    elif doc is not None and rev is not None:
        data = parse_documento_contenido(doc, rev)
    else:
        data = {}
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        nodes = build_default_organigrama_nodes(pptx_path=organigrama_pptx_path())
    else:
        nodes = organigrama_ensure_complete_nodes(nodes)
    return organigrama_tree(nodes)


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
            row = _organigrama_clean_node(n, i)
            if row:
                clean.append(row)
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


class DocumentoViewItem:
    """Adaptador para plantillas que esperan campos de anexo en documentos MSGI independientes."""

    def __init__(self, doc: SgiDocumento, rev: SgiProcedimientoRevision | None = None) -> None:
        self.id = doc.id
        self.codigo = doc.codigo
        self.nombre = doc.titulo
        self.revision = doc.revision or (rev.revision_label if rev else "")
        self.fecha_vigencia = rev.fecha_vigencia if rev else None
        self.tipo_contenido = doc.tipo_contenido
        self.archivo_path = doc.archivo_path


def documento_es_especial(doc: SgiDocumento | None) -> bool:
    if doc is None:
        return False
    return normalize_tipo_contenido(doc.tipo_contenido) in (
        ANEXO_TIPO_DOCUMENTO,
        ANEXO_TIPO_ORGANIGRAMA,
        ANEXO_TIPO_ARCHIVO,
    ) and bool((doc.tipo_contenido or "").strip())


def documento_view_item(doc: SgiDocumento, rev: SgiProcedimientoRevision | None) -> DocumentoViewItem:
    return DocumentoViewItem(doc, rev)


def parse_documento_contenido(doc: SgiDocumento, rev: SgiProcedimientoRevision) -> dict[str, Any]:
    try:
        data = json.loads(rev.contenido_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    tipo = normalize_tipo_contenido(doc.tipo_contenido)
    if tipo == ANEXO_TIPO_DOCUMENTO:
        base = default_documento_contenido(doc.titulo)
        base["titulo"] = (data.get("titulo") or doc.titulo or "").strip().upper()
        secs = data.get("secciones") if isinstance(data.get("secciones"), dict) else {}
        base["secciones"] = proc_svc.normalize_procedure_secciones(secs)
        return base
    if tipo == ANEXO_TIPO_ORGANIGRAMA:
        nodes = data.get("nodes")
        if not isinstance(nodes, list):
            nodes = []
        return {"version": int(data.get("version") or 1), "nodes": nodes}
    return data


def documento_payload_for_view(doc: SgiDocumento, rev: SgiProcedimientoRevision) -> dict[str, Any]:
    data = parse_documento_contenido(doc, rev)
    return {
        "titulo": data.get("titulo") or doc.titulo,
        "secciones": data.get("secciones") or {},
        "control_cambios": [],
        "registros": [],
        "anexos": [],
    }


def ensure_documento_tipo_contenido(
    doc: SgiDocumento,
    rev: SgiProcedimientoRevision,
    tipo: str,
    *,
    docx_path: Path | None = None,
    pptx_path: Path | None = None,
    refresh_organigrama: bool = False,
) -> None:
    doc.tipo_contenido = normalize_tipo_contenido(tipo)
    if doc.tipo_contenido == ANEXO_TIPO_DOCUMENTO:
        if not (rev.contenido_json or "").strip() or rev.contenido_json == "{}":
            if docx_path and docx_path.is_file():
                data = contenido_from_docx(docx_path, doc.titulo)
            else:
                data = default_documento_contenido(doc.titulo)
            rev.contenido_json = json.dumps(data, ensure_ascii=False)
    elif doc.tipo_contenido == ANEXO_TIPO_ORGANIGRAMA:
        empty = not (rev.contenido_json or "").strip() or rev.contenido_json == "{}"
        if empty or refresh_organigrama:
            preserve: dict[str, int] = {}
            if not empty:
                try:
                    prev = json.loads(rev.contenido_json or "{}")
                    for n in prev.get("nodes") or []:
                        if isinstance(n, dict) and n.get("id") and n.get("user_id"):
                            preserve[str(n["id"])] = int(n["user_id"])
                except (json.JSONDecodeError, TypeError, ValueError):
                    preserve = {}
            nodes = build_default_organigrama_nodes(preserve_users=preserve, pptx_path=pptx_path)
            rev.contenido_json = json.dumps({"version": 1, "nodes": nodes}, ensure_ascii=False)


def save_documento_contenido(doc_id: int, rev_id: int, payload: dict[str, Any]) -> tuple[bool, str]:
    doc = db.session.get(SgiDocumento, int(doc_id))
    rev = db.session.get(SgiProcedimientoRevision, int(rev_id))
    if doc is None or rev is None or rev.documento_id != doc.id:
        return False, "Documento no encontrado."
    if not documento_es_especial(doc):
        return False, "Este documento no admite edición de contenido especial."
    tipo = normalize_tipo_contenido(doc.tipo_contenido)
    if tipo == ANEXO_TIPO_DOCUMENTO:
        titulo = (payload.get("titulo") or doc.titulo or "").strip().upper()
        secciones = proc_svc.normalize_procedure_secciones(payload.get("secciones") or {})
        rev.contenido_json = json.dumps({"titulo": titulo, "secciones": secciones}, ensure_ascii=False)
        if titulo:
            doc.titulo = titulo[:512]
    elif tipo == ANEXO_TIPO_ORGANIGRAMA:
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            return False, "Estructura de organigrama inválida."
        clean: list[dict[str, Any]] = []
        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                continue
            row = _organigrama_clean_node(n, i)
            if row:
                clean.append(row)
        rev.contenido_json = json.dumps({"version": 1, "nodes": clean}, ensure_ascii=False)
    else:
        return False, "Este documento no admite edición de contenido."
    db.session.commit()
    return True, "Contenido guardado."
