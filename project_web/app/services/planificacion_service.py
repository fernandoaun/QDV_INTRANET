from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import Select, and_, delete, or_, select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import PlanificacionActividad, PlanificacionDependencia, User
from app.utils.datetime_operacion import now_operacion_naive_local

ESTADOS: tuple[str, ...] = ("pendiente", "en_curso", "finalizada", "demorada", "cancelada")
PRIORIDADES: tuple[str, ...] = ("baja", "media", "alta", "critica")
CATEGORIAS: tuple[str, ...] = (
    "produccion",
    "salmuera",
    "agua",
    "hipoclorito",
    "entregas",
    "mantenimiento",
    "logistica",
    "administracion",
    "otro",
)

TIPOS_DEPENDENCIA: tuple[str, ...] = ("FS", "SS", "FF", "SF")

ESTADO_LABELS: dict[str, str] = {
    "pendiente": "Pendiente",
    "en_curso": "En curso",
    "finalizada": "Finalizada",
    "demorada": "Demorada",
    "cancelada": "Cancelada",
}
PRIORIDAD_LABELS: dict[str, str] = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
    "critica": "Crítica",
}
CATEGORIA_LABELS: dict[str, str] = {
    "produccion": "Producción",
    "salmuera": "Salmuera",
    "agua": "Agua",
    "hipoclorito": "Hipoclorito",
    "entregas": "Entregas",
    "mantenimiento": "Mantenimiento",
    "logistica": "Logística",
    "administracion": "Administración",
    "otro": "Otro",
}
TIPO_DEPENDENCIA_LABELS: dict[str, str] = {
    "FS": "Fin → Inicio (FS)",
    "SS": "Inicio → Inicio (SS)",
    "FF": "Fin → Fin (FF)",
    "SF": "Inicio → Fin (SF)",
}

_PRIOR_ORDER: dict[str, int] = {"critica": 0, "alta": 1, "media": 2, "baja": 3}
_ESTADO_ORDER: dict[str, int] = {
    "demorada": 0,
    "en_curso": 1,
    "pendiente": 2,
    "finalizada": 3,
    "cancelada": 4,
}


def labels_context() -> dict[str, Any]:
    return {
        "estados": ESTADOS,
        "prioridades": PRIORIDADES,
        "categorias": CATEGORIAS,
        "estado_labels": ESTADO_LABELS,
        "prioridad_labels": PRIORIDAD_LABELS,
        "categoria_labels": CATEGORIA_LABELS,
        "tipos_dependencia": TIPOS_DEPENDENCIA,
        "tipo_dependencia_labels": TIPO_DEPENDENCIA_LABELS,
    }


def _today() -> date:
    return now_operacion_naive_local().date()


def actividad_display_codigo(row: PlanificacionActividad) -> str:
    c = (row.codigo or "").strip()
    if c:
        return c
    return f"#{row.id}"


def is_atrasada(row: PlanificacionActividad, today: date | None = None) -> bool:
    t = today or _today()
    if row.estado in ("finalizada", "cancelada"):
        return False
    return row.fecha_fin < t


def _pred_terminada(p: PlanificacionActividad) -> bool:
    return p.estado in ("finalizada", "cancelada")


def _pred_arranco(p: PlanificacionActividad) -> bool:
    return p.estado != "pendiente"


@dataclass
class ActividadFiltros:
    estado: str | None = None
    responsable_user_id: int | None = None
    categoria: str | None = None
    prioridad: str | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    q: str | None = None
    sort: str | None = None


def parse_filtros_from_request(values: Any) -> ActividadFiltros:
    def _int_or_none(raw: str | None) -> int | None:
        s = (raw or "").strip()
        return int(s) if s.isdigit() else None

    def _date_or_none(raw: str | None) -> date | None:
        s = (raw or "").strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None

    st = (values.get("estado") or "").strip() or None
    if st and st not in ESTADOS:
        st = None
    cat = (values.get("categoria") or "").strip() or None
    if cat and cat not in CATEGORIAS:
        cat = None
    pr = (values.get("prioridad") or "").strip() or None
    if pr and pr not in PRIORIDADES:
        pr = None
    sort = (values.get("sort") or "").strip() or None
    if sort not in ("inicio", "fin", "prioridad", "estado", None):
        sort = None
    return ActividadFiltros(
        estado=st,
        responsable_user_id=_int_or_none(values.get("responsable_user_id")),
        categoria=cat,
        prioridad=pr,
        fecha_desde=_date_or_none(values.get("fecha_desde")),
        fecha_hasta=_date_or_none(values.get("fecha_hasta")),
        q=(values.get("q") or "").strip() or None,
        sort=sort,
    )


def _apply_filtros(stmt: Select, f: ActividadFiltros) -> Select:
    conds: list[Any] = []
    if f.estado:
        conds.append(PlanificacionActividad.estado == f.estado)
    if f.responsable_user_id is not None:
        conds.append(PlanificacionActividad.responsable_user_id == f.responsable_user_id)
    if f.categoria:
        conds.append(PlanificacionActividad.categoria == f.categoria)
    if f.prioridad:
        conds.append(PlanificacionActividad.prioridad == f.prioridad)
    if f.fecha_desde is not None:
        conds.append(PlanificacionActividad.fecha_fin >= f.fecha_desde)
    if f.fecha_hasta is not None:
        conds.append(PlanificacionActividad.fecha_inicio <= f.fecha_hasta)
    if f.q:
        like = f"%{f.q}%"
        conds.append(
            or_(
                PlanificacionActividad.titulo.ilike(like),
                PlanificacionActividad.descripcion.ilike(like),
                PlanificacionActividad.observaciones.ilike(like),
                PlanificacionActividad.codigo.ilike(like),
            )
        )
    if conds:
        stmt = stmt.where(and_(*conds))
    return stmt


def list_actividades(f: ActividadFiltros | None = None) -> list[PlanificacionActividad]:
    f = f or ActividadFiltros()
    stmt = select(PlanificacionActividad).options(joinedload(PlanificacionActividad.responsable))
    stmt = _apply_filtros(stmt, f)
    rows = list(db.session.scalars(stmt).unique().all())
    if f.sort == "inicio":
        rows.sort(key=lambda r: (r.fecha_inicio, r.fecha_fin, r.id))
    elif f.sort == "fin":
        rows.sort(key=lambda r: (r.fecha_fin, r.fecha_inicio, r.id))
    elif f.sort == "prioridad":
        rows.sort(key=lambda r: (_PRIOR_ORDER.get(r.prioridad, 9), r.fecha_inicio, r.id))
    elif f.sort == "estado":
        rows.sort(key=lambda r: (_ESTADO_ORDER.get(r.estado, 9), r.fecha_inicio, r.id))
    else:
        rows.sort(key=lambda r: (r.fecha_inicio, r.fecha_fin, r.id))
    return rows


def list_actividades_for_pred_picker(exclude_id: int | None = None) -> list[PlanificacionActividad]:
    stmt = select(PlanificacionActividad).order_by(PlanificacionActividad.fecha_inicio.asc(), PlanificacionActividad.id.asc())
    if exclude_id is not None:
        stmt = stmt.where(PlanificacionActividad.id != int(exclude_id))
    return list(db.session.scalars(stmt).all())


def get_actividad_or_none(actividad_id: int) -> PlanificacionActividad | None:
    return db.session.get(PlanificacionActividad, int(actividad_id))


def list_users_for_responsable() -> list[User]:
    stmt = select(User).where(User.activo.is_(True)).order_by(User.username.asc())
    return list(db.session.scalars(stmt).all())


def dependencias_entrantes_por_sucesora(sucesora_ids: list[int]) -> dict[int, list[PlanificacionDependencia]]:
    if not sucesora_ids:
        return {}
    stmt = (
        select(PlanificacionDependencia)
        .where(PlanificacionDependencia.sucesora_id.in_(sucesora_ids))
        .options(joinedload(PlanificacionDependencia.predecesora))
    )
    rows = list(db.session.scalars(stmt).unique().all())
    out: dict[int, list[PlanificacionDependencia]] = defaultdict(list)
    for d in rows:
        out[int(d.sucesora_id)].append(d)
    return dict(out)


def dependencias_salientes_por_predecesora(pre_ids: list[int]) -> dict[int, list[PlanificacionDependencia]]:
    if not pre_ids:
        return {}
    stmt = (
        select(PlanificacionDependencia)
        .where(PlanificacionDependencia.predecesora_id.in_(pre_ids))
        .options(joinedload(PlanificacionDependencia.sucesora))
    )
    rows = list(db.session.scalars(stmt).unique().all())
    out: dict[int, list[PlanificacionDependencia]] = defaultdict(list)
    for d in rows:
        out[int(d.predecesora_id)].append(d)
    return dict(out)


def _all_edges_except_sucesora(sucesora_id: int) -> list[tuple[int, int]]:
    stmt = select(PlanificacionDependencia.predecesora_id, PlanificacionDependencia.sucesora_id).where(
        PlanificacionDependencia.sucesora_id != sucesora_id
    )
    return [(int(a), int(b)) for a, b in db.session.execute(stmt).all()]


def _directed_graph_has_cycle(edges: list[tuple[int, int]]) -> bool:
    """Detección de ciclo por ordenamiento topológico (Kahn)."""
    if not edges:
        return False
    g: dict[int, list[int]] = defaultdict(list)
    indeg: dict[int, int] = defaultdict(int)
    nodes: set[int] = set()
    for u, v in edges:
        g[u].append(v)
        indeg[v] += 1
        nodes.add(u)
        nodes.add(v)
    for n in nodes:
        indeg.setdefault(n, indeg.get(n, 0))
    from collections import deque

    q = deque(n for n in nodes if indeg[n] == 0)
    seen = 0
    while q:
        u = q.popleft()
        seen += 1
        for v in g[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return seen != len(nodes)


def _validate_edges_no_cycle(sucesora_id: int, nuevas: list[tuple[int, str, int]]) -> str | None:
    """nuevas: (predecesora_id, tipo, lag). Arista lógica predecesora → sucesora."""
    preds = [p for p, _, _ in nuevas]
    if len(preds) != len(set(preds)):
        return "No podés repetir la misma actividad predecesora más de una vez."
    edges = list(_all_edges_except_sucesora(sucesora_id))
    for p, _, _ in nuevas:
        if p == sucesora_id:
            return "Una actividad no puede depender de sí misma."
        edges.append((p, sucesora_id))
    if _directed_graph_has_cycle(edges):
        return "Las dependencias formarían un ciclo (orden circular). Revisá predecesoras y otras actividades que dependan de esta."
    return None


def dependencia_stubs_for_validation(pairs: list[tuple[int, str, int]]) -> list[Any]:
    """Objetos mínimos con .tipo y .predecesora para reutilizar validadores de estado."""
    stubs: list[Any] = []
    for pid, tipo, _lag in pairs:
        p = db.session.get(PlanificacionActividad, pid)
        if p is None:
            continue
        stubs.append(type("_DepStub", (), {"tipo": tipo, "predecesora": p})())
    return stubs


def parse_dependencias_form(form: Any, sucesora_id: int | None) -> tuple[list[tuple[int, str, int]], list[str]]:
    """Devuelve lista (predecesora_id, tipo, lag_dias) y errores de parseo."""
    errs: list[str] = []
    raw_ids = form.getlist("dep_pre_id")
    raw_tipos = form.getlist("dep_tipo")
    raw_lags = form.getlist("dep_lag")
    n = max(len(raw_ids), len(raw_tipos), len(raw_lags))
    out: list[tuple[int, str, int]] = []
    seen: set[int] = set()
    for i in range(n):
        rid = (raw_ids[i] if i < len(raw_ids) else "").strip()
        if not rid:
            continue
        if not rid.isdigit():
            errs.append(f"Predecesora inválida en fila {i + 1}.")
            continue
        pid = int(rid)
        if sucesora_id is not None and pid == int(sucesora_id):
            errs.append("No podés seleccionar la misma actividad como predecesora.")
            continue
        if pid in seen:
            continue
        seen.add(pid)
        tipo = (raw_tipos[i] if i < len(raw_tipos) else "FS").strip().upper() or "FS"
        if tipo not in TIPOS_DEPENDENCIA:
            errs.append(f"Tipo de dependencia inválido para predecesora #{pid}.")
            continue
        lag_raw = (raw_lags[i] if i < len(raw_lags) else "0").strip() or "0"
        try:
            lag = int(lag_raw)
        except ValueError:
            errs.append(f"Desfase (días) inválido para predecesora #{pid}.")
            continue
        lag = max(-366, min(366, lag))
        out.append((pid, tipo, lag))
    return out, errs


def validate_predecesoras_existen(pairs: list[tuple[int, str, int]]) -> list[str]:
    errs: list[str] = []
    for pid, _, _ in pairs:
        if db.session.get(PlanificacionActividad, pid) is None:
            errs.append(f"La actividad predecesora #{pid} no existe.")
    return errs


def replace_dependencias_sucesora(sucesora_id: int, pairs: list[tuple[int, str, int]]) -> str | None:
    """
    Reemplaza todas las dependencias entrantes de `sucesora_id`.
    Retorna mensaje de error o None si OK.
    """
    sucesora_id = int(sucesora_id)
    errs = validate_predecesoras_existen(pairs)
    if errs:
        return errs[0]
    cyc = _validate_edges_no_cycle(sucesora_id, pairs)
    if cyc:
        return cyc
    db.session.execute(delete(PlanificacionDependencia).where(PlanificacionDependencia.sucesora_id == sucesora_id))
    for pid, tipo, lag in pairs:
        db.session.add(
            PlanificacionDependencia(
                predecesora_id=int(pid),
                sucesora_id=sucesora_id,
                tipo=tipo,
                lag_dias=int(lag),
            )
        )
    return None


def analizar_dependencias_sucesora(
    sucesora: PlanificacionActividad,
    deps: list[PlanificacionDependencia],
) -> dict[str, Any]:
    """
    - bloquea_inicio: no debería pasarse a «en curso» (reglas FS/SS).
    - bloquea_cierre: no debería pasarse a «finalizada» (FF/SF).
    - mensajes: texto para UI.
    """
    mensajes: list[str] = []
    bloquea_inicio = False
    bloquea_cierre = False
    for d in deps:
        p = d.predecesora
        label_p = actividad_display_codigo(p)
        if d.tipo == "FS":
            if not _pred_terminada(p):
                bloquea_inicio = True
                mensajes.append(f"FS: «{label_p}» aún no finalizada ({ESTADO_LABELS.get(p.estado, p.estado)}).")
        elif d.tipo == "SS":
            if not _pred_arranco(p):
                bloquea_inicio = True
                mensajes.append(f"SS: «{label_p}» aún no iniciada.")
        elif d.tipo == "FF":
            if not _pred_terminada(p):
                bloquea_cierre = True
                mensajes.append(f"FF: «{label_p}» debe finalizar antes de cerrar esta tarea.")
        elif d.tipo == "SF":
            if not _pred_arranco(p):
                bloquea_cierre = True
                mensajes.append(f"SF: «{label_p}» debe haber iniciado antes de cerrar esta tarea.")
    return {
        "bloquea_inicio": bloquea_inicio,
        "bloquea_cierre": bloquea_cierre,
        "mensajes": mensajes,
        "n_deps": len(deps),
    }


def resumen_predecesoras_texto(deps: list[PlanificacionDependencia]) -> str:
    if not deps:
        return "—"
    parts: list[str] = []
    for d in deps:
        p = d.predecesora
        parts.append(f"{d.tipo} {actividad_display_codigo(p)}")
    return ", ".join(parts)


def validate_estado_con_dependencias(
    sucesora: PlanificacionActividad,
    estado_anterior: str,
    estado_nuevo: str,
    deps: list[PlanificacionDependencia],
) -> str | None:
    """Retorna mensaje de error si el cambio de estado viola dependencias."""
    if estado_nuevo == estado_anterior:
        return None
    if estado_nuevo == "en_curso":
        for d in deps:
            p = d.predecesora
            if d.tipo == "FS" and not _pred_terminada(p):
                return (
                    f"No se puede poner «En curso»: la predecesora «{actividad_display_codigo(p)}» "
                    f"(FS) debe estar finalizada o cancelada. Estado actual: {ESTADO_LABELS.get(p.estado, p.estado)}."
                )
            if d.tipo == "SS" and p.estado == "pendiente":
                return (
                    f"No se puede poner «En curso»: la predecesora «{actividad_display_codigo(p)}» "
                    f"(SS) debe haber iniciado (no puede estar pendiente)."
                )
    if estado_nuevo == "finalizada":
        for d in deps:
            p = d.predecesora
            if d.tipo == "FF" and not _pred_terminada(p):
                return (
                    f"No se puede finalizar: la predecesora «{actividad_display_codigo(p)}» (FF) "
                    f"debe estar finalizada o cancelada primero."
                )
            if d.tipo == "SF" and p.estado == "pendiente":
                return (
                    f"No se puede finalizar: la predecesora «{actividad_display_codigo(p)}» (SF) "
                    f"debe haber iniciado antes."
                )
    return None


def _parse_date_required(raw: str | None, field: str) -> tuple[date | None, str | None]:
    s = (raw or "").strip()
    if not s:
        return None, f"{field} es obligatoria."
    try:
        return date.fromisoformat(s), None
    except ValueError:
        return None, f"{field} tiene formato inválido (usá AAAA-MM-DD)."


def validate_and_build_from_form(
    form: Any,
    *,
    existing: PlanificacionActividad | None = None,
    deps_entrantes: list[PlanificacionDependencia] | None = None,
) -> tuple[PlanificacionActividad | None, list[str]]:
    errors: list[str] = []
    titulo = (form.get("titulo") or "").strip()
    if not titulo:
        errors.append("El título es obligatorio.")

    fi, err_i = _parse_date_required(form.get("fecha_inicio"), "Fecha de inicio")
    if err_i:
        errors.append(err_i)
    ff, err_f = _parse_date_required(form.get("fecha_fin"), "Fecha de fin")
    if err_f:
        errors.append(err_f)
    if fi and ff and ff < fi:
        errors.append("La fecha de fin no puede ser anterior a la fecha de inicio.")

    estado = (form.get("estado") or "").strip() or "pendiente"
    if estado not in ESTADOS:
        errors.append("Estado inválido.")
    prioridad = (form.get("prioridad") or "").strip() or "media"
    if prioridad not in PRIORIDADES:
        errors.append("Prioridad inválida.")
    categoria = (form.get("categoria") or "").strip() or "otro"
    if categoria not in CATEGORIAS:
        errors.append("Categoría inválida.")

    codigo = (form.get("codigo") or "").strip() or None
    if codigo:
        q = select(PlanificacionActividad.id).where(PlanificacionActividad.codigo == codigo)
        if existing is not None:
            q = q.where(PlanificacionActividad.id != existing.id)
        dup = db.session.scalar(q)
        if dup is not None:
            errors.append("Ya existe otra actividad con ese código.")

    resp_raw = (form.get("responsable_user_id") or "").strip()
    responsable_user_id: int | None
    if not resp_raw:
        responsable_user_id = None
    elif resp_raw.isdigit():
        responsable_user_id = int(resp_raw)
        if db.session.get(User, responsable_user_id) is None:
            errors.append("Responsable inexistente.")
    else:
        errors.append("Responsable inválido.")

    descripcion = (form.get("descripcion") or "").strip() or None
    observaciones = (form.get("observaciones") or "").strip() or None
    linked_entity_type = (form.get("linked_entity_type") or "").strip() or None
    if linked_entity_type and len(linked_entity_type) > 32:
        errors.append("Tipo de vínculo demasiado largo.")
    linked_entity_id_raw = (form.get("linked_entity_id") or "").strip()
    linked_entity_id: int | None
    if not linked_entity_id_raw:
        linked_entity_id = None
    elif linked_entity_id_raw.lstrip("-").isdigit():
        linked_entity_id = int(linked_entity_id_raw)
    else:
        linked_entity_id = None
        errors.append("ID de entidad vinculada inválido.")

    if errors:
        return None, errors

    assert fi is not None and ff is not None
    dur = PlanificacionActividad.compute_duracion_dias(fi, ff)

    row = existing or PlanificacionActividad()
    estado_anterior = existing.estado if existing is not None else "pendiente"
    row.codigo = codigo
    row.titulo = titulo
    row.descripcion = descripcion
    row.fecha_inicio = fi
    row.fecha_fin = ff
    row.duracion_dias = dur
    row.responsable_user_id = responsable_user_id
    row.categoria = categoria
    row.prioridad = prioridad
    row.estado = estado
    row.observaciones = observaciones
    row.linked_entity_type = linked_entity_type
    row.linked_entity_id = linked_entity_id

    if deps_entrantes is not None:
        v = validate_estado_con_dependencias(row, estado_anterior, estado, deps_entrantes)
        if v:
            errors.append(v)

    if errors:
        return None, errors
    return row, []


def gantt_tasks_for_rows(
    rows: Iterable[PlanificacionActividad],
    *,
    deps_por_sucesora: dict[int, list[PlanificacionDependencia]] | None = None,
) -> list[dict[str, Any]]:
    """
    Tareas para Frappe Gantt: `end` exclusivo.
    `dependencies`: solo tipo FS (semántica Finish→Start de la librería).
    """
    rows_list = list(rows)
    ids = [r.id for r in rows_list]
    deps_map = deps_por_sucesora if deps_por_sucesora is not None else dependencias_entrantes_por_sucesora(ids)
    today = _today()
    out: list[dict[str, Any]] = []
    for r in rows_list:
        end_excl = r.fecha_fin + timedelta(days=1)
        classes: list[str] = [f"gantt-estado-{r.estado}"]
        if is_atrasada(r, today):
            classes.append("gantt-atrasada")
        deps = deps_map.get(int(r.id), [])
        anal = analizar_dependencias_sucesora(r, deps)
        if anal["bloquea_inicio"] and r.estado == "pendiente":
            classes.append("gantt-dep-bloqueada")
        dep_fs_ids = [str(d.predecesora_id) for d in deps if d.tipo == "FS"]
        dep_all_txt = resumen_predecesoras_texto(deps)
        out.append(
            {
                "id": str(r.id),
                "name": actividad_display_codigo(r) + " — " + (r.titulo or "")[:80],
                "start": r.fecha_inicio.isoformat(),
                "end": end_excl.isoformat(),
                "progress": 100 if r.estado == "finalizada" else (50 if r.estado == "en_curso" else 0),
                "dependencies": ",".join(dep_fs_ids) if dep_fs_ids else "",
                "custom_class": " ".join(classes),
                "edit_url": None,
                "meta": {
                    "titulo": r.titulo,
                    "estado": r.estado,
                    "prioridad": r.prioridad,
                    "categoria": r.categoria,
                    "fecha_inicio": r.fecha_inicio.isoformat(),
                    "fecha_fin": r.fecha_fin.isoformat(),
                    "duracion_dias": r.duracion_dias,
                    "observaciones": r.observaciones or "",
                    "dependencias": dep_all_txt,
                    "dependencias_detalle": anal["mensajes"],
                    "dep_bloquea_inicio": anal["bloquea_inicio"],
                },
            }
        )
    return out


def export_csv_bytes(rows: Iterable[PlanificacionActividad]) -> bytes:
    rows_list = list(rows)
    ids = [r.id for r in rows_list]
    deps_map = dependencias_entrantes_por_sucesora(ids)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(
        [
            "codigo",
            "titulo",
            "descripcion",
            "fecha_inicio",
            "fecha_fin",
            "duracion_dias",
            "responsable_username",
            "categoria",
            "prioridad",
            "estado",
            "observaciones",
            "linked_entity_type",
            "linked_entity_id",
            "predecesoras",
        ]
    )
    for r in rows_list:
        ru = ""
        if r.responsable_user_id and r.responsable is not None:
            ru = (r.responsable.username or "").strip()
        pred_txt = resumen_predecesoras_texto(deps_map.get(int(r.id), []))
        w.writerow(
            [
                actividad_display_codigo(r),
                r.titulo,
                (r.descripcion or "").replace("\n", " ").replace("\r", " "),
                r.fecha_inicio.isoformat(),
                r.fecha_fin.isoformat(),
                str(r.duracion_dias),
                ru,
                r.categoria,
                r.prioridad,
                r.estado,
                (r.observaciones or "").replace("\n", " ").replace("\r", " "),
                r.linked_entity_type or "",
                r.linked_entity_id if r.linked_entity_id is not None else "",
                pred_txt,
            ]
        )
    raw = buf.getvalue().encode("utf-8-sig")
    return raw
