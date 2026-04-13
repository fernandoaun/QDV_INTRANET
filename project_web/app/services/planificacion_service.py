from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import PlanificacionActividad, User
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


@dataclass
class ActividadFiltros:
    estado: str | None = None
    responsable_user_id: int | None = None
    categoria: str | None = None
    prioridad: str | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    q: str | None = None
    sort: str | None = None  # inicio | fin | prioridad | estado


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


def get_actividad_or_none(actividad_id: int) -> PlanificacionActividad | None:
    return db.session.get(PlanificacionActividad, int(actividad_id))


def list_users_for_responsable() -> list[User]:
    stmt = select(User).where(User.activo.is_(True)).order_by(User.username.asc())
    return list(db.session.scalars(stmt).all())


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
    return row, []


def gantt_tasks_for_rows(rows: Iterable[PlanificacionActividad]) -> list[dict[str, Any]]:
    """
    Tareas para Frappe Gantt: `end` exclusivo (día siguiente al último día inclusive).
    """
    out: list[dict[str, Any]] = []
    today = _today()
    for r in rows:
        end_excl = r.fecha_fin + timedelta(days=1)
        classes: list[str] = [f"gantt-estado-{r.estado}"]
        if is_atrasada(r, today):
            classes.append("gantt-atrasada")
        out.append(
            {
                "id": str(r.id),
                "name": actividad_display_codigo(r) + " — " + (r.titulo or "")[:80],
                "start": r.fecha_inicio.isoformat(),
                "end": end_excl.isoformat(),
                "progress": 100 if r.estado == "finalizada" else (50 if r.estado == "en_curso" else 0),
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
                },
            }
        )
    return out


def export_csv_bytes(rows: Iterable[PlanificacionActividad]) -> bytes:
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
        ]
    )
    for r in rows:
        ru = ""
        if r.responsable_user_id and r.responsable is not None:
            ru = (r.responsable.username or "").strip()
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
            ]
        )
    raw = buf.getvalue().encode("utf-8-sig")
    return raw
