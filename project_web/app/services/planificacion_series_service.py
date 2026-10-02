"""Tareas repetitivas de Planificación.

Una serie es una regla (cada N días/semanas/meses/años, ciertos días de la semana, ciertos días del mes o
ciertos meses del año) más una plantilla de tarea. Sus ocurrencias son actividades con el mismo `serie_id`.

- Con fin (N veces o hasta una fecha) se crean todas al guardar.
- Sin fin se mantienen programados los próximos `HORIZONTE_MESES`; `extender_series()` agrega las que van
  faltando (lo llaman las pantallas de Planificación y el trabajo diario de avisos).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any, Iterator

from sqlalchemy import func, select

from app.extensions import db
from app.models import PlanificacionActividad, PlanificacionSerie

MODOS: tuple[str, ...] = ("intervalo", "dias_semana", "dias_mes", "meses_anio")
UNIDADES: tuple[str, ...] = ("dias", "semanas", "meses", "anios")
UNIDAD_LABELS = {"dias": "día(s)", "semanas": "semana(s)", "meses": "mes(es)", "anios": "año(s)"}
DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
MESES = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
MAX_OCURRENCIAS = 400
HORIZONTE_MESES = 12


@dataclass
class Repeticion:
    intervalo: int = 1
    unidad: str = "semanas"
    hasta: date | None = None
    veces: int | None = None
    modo: str = "intervalo"
    dias_semana: tuple[int, ...] = field(default_factory=tuple)  # 0 = lunes
    dias_mes: tuple[int, ...] = field(default_factory=tuple)
    meses: tuple[int, ...] = field(default_factory=tuple)  # 1 = enero
    sin_fin: bool = False

    def to_json(self) -> str:
        d = asdict(self)
        d["hasta"] = self.hasta.isoformat() if self.hasta else None
        return json.dumps(d)

    @classmethod
    def from_json(cls, raw: str) -> "Repeticion":
        d = json.loads(raw or "{}")
        d["hasta"] = date.fromisoformat(d["hasta"]) if d.get("hasta") else None
        for k in ("dias_semana", "dias_mes", "meses"):
            d[k] = tuple(d.get(k) or ())
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def labels_context() -> dict[str, Any]:
    return {
        "repeticion_modos": MODOS,
        "repeticion_unidades": UNIDADES,
        "repeticion_unidad_labels": UNIDAD_LABELS,
        "repeticion_dias_semana": DIAS_SEMANA,
        "repeticion_meses": MESES,
        "repeticion_max": MAX_OCURRENCIAS,
        "repeticion_horizonte_meses": HORIZONTE_MESES,
    }


# ---------------------------------------------------------------- fechas


def _ultimo_dia(y: int, m: int) -> int:
    return ((date(y + m // 12, m % 12 + 1, 1)) - timedelta(days=1)).day


def _add_months(d: date, months: int, dia_ancla: int) -> date:
    """Suma meses conservando el día de origen; si el mes es más corto, usa su último día (31 → 30/28)."""
    total = d.year * 12 + (d.month - 1) + months
    y, m = divmod(total, 12)
    m += 1
    return date(y, m, min(dia_ancla, _ultimo_dia(y, m)))


def ocurrencias(ancla: date, rep: Repeticion) -> Iterator[date]:
    """Fechas de inicio de la serie desde `ancla` (inclusive), en orden y sin fin (el llamador corta)."""
    paso = max(1, int(rep.intervalo or 1))
    k = 0
    if rep.modo == "dias_semana":
        lunes = ancla - timedelta(days=ancla.weekday())
        dias = sorted(set(rep.dias_semana))
        while True:
            semana = lunes + timedelta(weeks=k * paso)
            for d in dias:
                dt = semana + timedelta(days=d)
                if dt >= ancla:
                    yield dt
            k += 1
    elif rep.modo == "dias_mes":
        dias = sorted(set(rep.dias_mes))
        base = ancla.replace(day=1)
        while True:
            mes = _add_months(base, k * paso, 1)
            ult = _ultimo_dia(mes.year, mes.month)
            for dt in sorted({mes.replace(day=min(d, ult)) for d in dias}):
                if dt >= ancla:
                    yield dt
            k += 1
    elif rep.modo == "meses_anio":
        meses = sorted(set(rep.meses))
        while True:
            y = ancla.year + k * paso
            for m in meses:
                dt = date(y, m, min(ancla.day, _ultimo_dia(y, m)))
                if dt >= ancla:
                    yield dt
            k += 1
    else:
        while True:
            if rep.unidad == "dias":
                yield ancla + timedelta(days=k * paso)
            elif rep.unidad == "semanas":
                yield ancla + timedelta(weeks=k * paso)
            else:
                yield _add_months(ancla, k * paso * (12 if rep.unidad == "anios" else 1), ancla.day)
            k += 1


def horizonte(hoy: date | None = None) -> date:
    from app.utils.datetime_operacion import now_operacion_naive_local

    hoy = hoy or now_operacion_naive_local().date()
    return _add_months(hoy, HORIZONTE_MESES, hoy.day)


def fechas_repeticion(
    fecha_inicio: date, fecha_fin: date, rep: Repeticion, *, hasta_horizonte: date | None = None
) -> tuple[list[tuple[date, date]], str | None]:
    """(inicio, fin) de cada ocurrencia desde `fecha_inicio`. Cada una conserva la duración de la original."""
    dur = fecha_fin - fecha_inicio
    limite = rep.hasta
    if rep.sin_fin:
        limite = hasta_horizonte or horizonte()
    out: list[tuple[date, date]] = []
    for ini in ocurrencias(fecha_inicio, rep):
        if rep.veces is not None and not rep.sin_fin and len(out) >= rep.veces:
            break
        if limite is not None and ini > limite:
            break
        if len(out) >= MAX_OCURRENCIAS:
            if rep.sin_fin:
                break
            return [], (
                f"La repetición generaría más de {MAX_OCURRENCIAS} actividades. "
                "Acortá la fecha «hasta» o espaciá más las repeticiones."
            )
        out.append((ini, ini + dur))
    if not out:
        return [], "Con esa configuración no hay ninguna fecha para programar."
    if len(out) < 2 and not rep.sin_fin:
        return [], "Con esa fecha «hasta» la actividad no llega a repetirse ni una vez."
    return out, None


def describir(rep: Repeticion) -> str:
    cada = int(rep.intervalo or 1)
    if rep.modo == "dias_semana":
        dias = " y ".join(DIAS_SEMANA[d] for d in sorted(rep.dias_semana))
        txt = f"{dias} " + ("cada semana" if cada == 1 else f"cada {cada} semanas")
    elif rep.modo == "dias_mes":
        dias = " y ".join(str(d) for d in sorted(rep.dias_mes))
        txt = f"días {dias} " + ("de cada mes" if cada == 1 else f"cada {cada} meses")
    elif rep.modo == "meses_anio":
        meses = " y ".join(MESES[m - 1] for m in sorted(rep.meses))
        txt = f"{meses} " + ("de cada año" if cada == 1 else f"cada {cada} años")
    else:
        txt = f"cada {cada} {UNIDAD_LABELS.get(rep.unidad, rep.unidad)}"
    if rep.sin_fin:
        return txt + ", sin fin"
    if rep.veces:
        return txt + f", {rep.veces} veces"
    if rep.hasta:
        return txt + f", hasta {rep.hasta.strftime('%d/%m/%Y')}"
    return txt


def describir_serie(serie_id: str | None) -> str:
    s = db.session.get(PlanificacionSerie, serie_id) if serie_id else None
    if s is None:
        return ""
    txt = describir(Repeticion.from_json(s.regla_json))
    return txt + ("" if s.activa or not Repeticion.from_json(s.regla_json).sin_fin else " (detenida)")


# ---------------------------------------------------------------- formulario


def _enteros(valores: list[str], lo: int, hi: int) -> tuple[int, ...]:
    out = set()
    for v in valores:
        for parte in str(v).replace(";", ",").split(","):
            parte = parte.strip()
            if parte.isdigit() and lo <= int(parte) <= hi:
                out.add(int(parte))
    return tuple(sorted(out))


def parse_repeticion_form(form: Any, fecha_inicio: date | None) -> tuple[Repeticion | None, list[str]]:
    """Lee los campos de repetición. Devuelve (None, []) si la actividad no se repite."""
    if (form.get("repetir") or "").strip() not in ("1", "on", "true"):
        return None, []
    getlist = getattr(form, "getlist", lambda k: [form.get(k)] if form.get(k) is not None else [])
    errors: list[str] = []
    modo = (form.get("rep_modo") or "intervalo").strip()
    if modo not in MODOS:
        errors.append("Repetición: modo inválido.")
    raw_int = (form.get("rep_intervalo") or "1").strip()
    intervalo = int(raw_int) if raw_int.isdigit() else 0
    if not 1 <= intervalo <= 100:
        errors.append("Repetición: «cada» tiene que ser un número entre 1 y 100.")
    unidad = (form.get("rep_unidad") or "semanas").strip()
    if modo == "intervalo" and unidad not in UNIDADES:
        errors.append("Repetición: elegí días, semanas, meses o años.")
    dias_semana = _enteros(getlist("rep_dias_semana"), 0, 6)
    dias_mes = _enteros(getlist("rep_dias_mes"), 1, 31)
    meses = _enteros(getlist("rep_meses"), 1, 12)
    if modo == "dias_semana" and not dias_semana:
        errors.append("Repetición: marcá al menos un día de la semana.")
    if modo == "dias_mes" and not dias_mes:
        errors.append("Repetición: indicá los días del mes (por ejemplo 1, 15).")
    if modo == "meses_anio" and not meses:
        errors.append("Repetición: marcá al menos un mes.")
    fin = (form.get("rep_fin") or "sin_fin").strip()
    hasta: date | None = None
    veces: int | None = None
    if fin == "hasta":
        raw = (form.get("rep_hasta") or "").strip()
        try:
            hasta = date.fromisoformat(raw)
        except ValueError:
            errors.append("Repetición: indicá la fecha «hasta».")
        else:
            if fecha_inicio and hasta < fecha_inicio:
                errors.append("Repetición: la fecha «hasta» no puede ser anterior a la fecha de inicio.")
    elif fin == "veces":
        raw_veces = (form.get("rep_veces") or "").strip()
        veces = int(raw_veces) if raw_veces.isdigit() else 0
        if not 2 <= veces <= MAX_OCURRENCIAS:
            errors.append(f"Repetición: la cantidad de veces tiene que estar entre 2 y {MAX_OCURRENCIAS}.")
    if errors:
        return None, errors
    return (
        Repeticion(
            intervalo=intervalo, unidad=unidad, hasta=hasta, veces=veces, modo=modo,
            dias_semana=dias_semana, dias_mes=dias_mes, meses=meses, sin_fin=(fin == "sin_fin"),
        ),
        [],
    )


# ---------------------------------------------------------------- creación y extensión


def _codigo(base: str | None, n: int, ancho: int | None) -> str | None:
    if not base:
        return None
    return f"{base}-{n:0{ancho}d}" if ancho else f"{base}-{n}"


def _nueva_ocurrencia(serie: PlanificacionSerie, ini: date, codigo: str | None) -> PlanificacionActividad:
    fin = ini + timedelta(days=max(0, int(serie.duracion_dias or 1) - 1))
    return PlanificacionActividad(
        codigo=codigo,
        titulo=serie.titulo,
        descripcion=serie.descripcion,
        fecha_inicio=ini,
        fecha_fin=fin,
        duracion_dias=PlanificacionActividad.compute_duracion_dias(ini, fin),
        responsable_user_id=serie.responsable_user_id,
        categoria=serie.categoria,
        prioridad=serie.prioridad,
        estado="pendiente",
        observaciones=serie.observaciones,
        created_by_user_id=serie.created_by_user_id,
        serie_id=serie.id,
    )


def crear_repeticiones(
    primera: PlanificacionActividad, fechas: list[tuple[date, date]], rep: Repeticion | None = None
) -> tuple[list[PlanificacionActividad], str | None]:
    """Guarda la regla, ubica `primera` en la primera fecha y agrega las demás ocurrencias. No hace commit."""
    rep = rep or Repeticion()
    serie = PlanificacionSerie(
        id=uuid.uuid4().hex,
        regla_json=rep.to_json(),
        ancla=fechas[0][0],
        duracion_dias=primera.duracion_dias,
        generada_hasta=(horizonte() if rep.sin_fin else fechas[-1][0]),
        ocurrencias_generadas=len(fechas),
        activa=bool(rep.sin_fin),
        codigo_base=(primera.codigo or None),
        titulo=primera.titulo,
        descripcion=primera.descripcion,
        responsable_user_id=primera.responsable_user_id,
        categoria=primera.categoria,
        prioridad=primera.prioridad,
        observaciones=primera.observaciones,
        created_by_user_id=primera.created_by_user_id,
    )
    ancho = None if rep.sin_fin else len(str(len(fechas)))
    codigos = [_codigo(serie.codigo_base, i + 1, ancho) for i in range(len(fechas))]
    if serie.codigo_base:
        if any(c and len(c) > 64 for c in codigos):
            return [], "El código es demasiado largo para numerar las repeticiones."
        dup = db.session.scalar(select(PlanificacionActividad.codigo).where(PlanificacionActividad.codigo.in_(codigos)))
        if dup is not None:
            return [], f"Ya existe una actividad con el código {dup}."
    db.session.add(serie)
    primera.serie_id = serie.id
    primera.codigo = codigos[0]
    primera.fecha_inicio, primera.fecha_fin = fechas[0]
    copias: list[PlanificacionActividad] = []
    for (ini, _fin), cod in zip(fechas[1:], codigos[1:]):
        c = _nueva_ocurrencia(serie, ini, cod)
        c.linked_entity_type, c.linked_entity_id = primera.linked_entity_type, primera.linked_entity_id
        db.session.add(c)
        copias.append(c)
    return copias, None


def extender_series(hoy: date | None = None) -> int:
    """Agrega a las series sin fin las ocurrencias que faltan hasta el horizonte. Devuelve cuántas creó."""
    limite = horizonte(hoy)
    pendientes = db.session.scalars(
        select(PlanificacionSerie).where(
            PlanificacionSerie.activa.is_(True),
            (PlanificacionSerie.generada_hasta.is_(None)) | (PlanificacionSerie.generada_hasta < limite),
        )
    ).all()
    creadas = 0
    for serie in pendientes:
        rep = Repeticion.from_json(serie.regla_json)
        if not rep.sin_fin:
            continue
        existentes = set(
            db.session.scalars(
                select(PlanificacionActividad.fecha_inicio).where(PlanificacionActividad.serie_id == serie.id)
            )
        )
        desde = serie.generada_hasta or serie.ancla
        for ini in ocurrencias(serie.ancla, rep):
            if ini > limite:
                break
            if ini <= desde or ini in existentes:
                continue
            serie.ocurrencias_generadas += 1
            db.session.add(_nueva_ocurrencia(serie, ini, _codigo(serie.codigo_base, serie.ocurrencias_generadas, None)))
            creadas += 1
        serie.generada_hasta = limite
    if pendientes:
        db.session.commit()
    return creadas


def serie_restantes(row: PlanificacionActividad) -> list[PlanificacionActividad]:
    """Esta actividad y las siguientes de su serie (por fecha de inicio)."""
    if not row.serie_id:
        return [row]
    stmt = (
        select(PlanificacionActividad)
        .where(
            PlanificacionActividad.serie_id == row.serie_id,
            PlanificacionActividad.fecha_inicio >= row.fecha_inicio,
        )
        .order_by(PlanificacionActividad.fecha_inicio)
    )
    return list(db.session.scalars(stmt).unique())


def detener_serie(serie_id: str | None) -> None:
    """Corta la repetición (no se programan más). No hace commit."""
    s = db.session.get(PlanificacionSerie, serie_id) if serie_id else None
    if s is not None:
        s.activa = False


def contar_serie(serie_id: str | None) -> int:
    if not serie_id:
        return 0
    return int(
        db.session.scalar(
            select(func.count(PlanificacionActividad.id)).where(PlanificacionActividad.serie_id == serie_id)
        )
        or 0
    )
