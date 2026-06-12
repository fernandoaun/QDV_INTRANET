from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_

from app.extensions import db
from app.models import (
    EmpleadoPersonal,
    PersonalApercibimiento,
    PersonalArt,
    PersonalCurso,
    PersonalEntregaEpp,
    PersonalEppItem,
    PersonalVacacion,
)
from app.utils.datetime_operacion import now_operacion_naive_local


def today_operacion() -> date:
    return now_operacion_naive_local().date()

ESTADOS_EMPLEADO = ("activo", "baja")
ESTADOS_VACACION = ("pendiente", "tomada", "cancelada")
TIPOS_APERCIBIMIENTO = ("verbal", "escrito")
CATEGORIAS_EPP = ("ropa", "epp", "otro")

ESTADO_EMPLEADO_LABELS = {"activo": "Activo", "baja": "Baja"}
ESTADO_VACACION_LABELS = {"pendiente": "Pendiente", "tomada": "Tomada", "cancelada": "Cancelada"}
TIPO_APERCIBIMIENTO_LABELS = {"verbal": "Verbal", "escrito": "Escrito"}
CATEGORIA_EPP_LABELS = {"ropa": "Ropa", "epp": "EPP", "otro": "Otro"}


def parse_iso_date(raw: str | None) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _dias_entre(desde: date, hasta: date) -> int:
    return max(1, (hasta - desde).days + 1)


def dashboard_counts() -> dict[str, int]:
    hoy = today_operacion()

    activos = (
        db.session.query(func.count(EmpleadoPersonal.id))
        .filter(EmpleadoPersonal.estado == "activo")
        .scalar()
        or 0
    )
    cumple_mes = (
        db.session.query(func.count(EmpleadoPersonal.id))
        .filter(
            EmpleadoPersonal.estado == "activo",
            EmpleadoPersonal.fecha_nacimiento.isnot(None),
            func.extract("month", EmpleadoPersonal.fecha_nacimiento) == hoy.month,
        )
        .scalar()
        or 0
    )
    cursos_por_vencer = (
        db.session.query(func.count(PersonalCurso.id))
        .join(EmpleadoPersonal)
        .filter(
            EmpleadoPersonal.estado == "activo",
            PersonalCurso.fecha_vencimiento.isnot(None),
            PersonalCurso.fecha_vencimiento <= hoy + timedelta(days=30),
            PersonalCurso.fecha_vencimiento >= hoy,
        )
        .scalar()
        or 0
    )
    vac_pendientes = (
        db.session.query(func.count(PersonalVacacion.id))
        .filter(PersonalVacacion.estado == "pendiente")
        .scalar()
        or 0
    )
    vac_tomadas_anio = (
        db.session.query(func.count(PersonalVacacion.id))
        .filter(PersonalVacacion.estado == "tomada", PersonalVacacion.anio == hoy.year)
        .scalar()
        or 0
    )
    aperc_anio = (
        db.session.query(func.count(PersonalApercibimiento.id))
        .filter(
            PersonalApercibimiento.fecha >= date(hoy.year, 1, 1),
            PersonalApercibimiento.fecha <= date(hoy.year, 12, 31),
        )
        .scalar()
        or 0
    )
    return {
        "empleados_activos": int(activos),
        "cumpleanos_mes": int(cumple_mes),
        "cursos_por_vencer": int(cursos_por_vencer),
        "vacaciones_pendientes": int(vac_pendientes),
        "vacaciones_tomadas_anio": int(vac_tomadas_anio),
        "apercibimientos_anio": int(aperc_anio),
        "items_epp_activos": int(
            db.session.query(func.count(PersonalEppItem.id)).filter(PersonalEppItem.activo.is_(True)).scalar() or 0
        ),
    }


def proximos_cumpleanos(dias: int = 30) -> list[EmpleadoPersonal]:
    hoy = today_operacion()
    empleados = (
        db.session.query(EmpleadoPersonal)
        .filter(EmpleadoPersonal.estado == "activo", EmpleadoPersonal.fecha_nacimiento.isnot(None))
        .order_by(EmpleadoPersonal.apellido, EmpleadoPersonal.nombre)
        .all()
    )
    out: list[tuple[int, EmpleadoPersonal]] = []
    for e in empleados:
        fn = e.fecha_nacimiento
        if fn is None:
            continue
        try:
            prox = fn.replace(year=hoy.year)
        except ValueError:
            prox = date(hoy.year, 2, 28)
        if prox < hoy:
            try:
                prox = fn.replace(year=hoy.year + 1)
            except ValueError:
                prox = date(hoy.year + 1, 2, 28)
        delta = (prox - hoy).days
        if 0 <= delta <= dias:
            out.append((delta, e))
    out.sort(key=lambda x: (x[0], x[1].apellido, x[1].nombre))
    return [e for _, e in out]


def list_empleados(*, q: str = "", estado: str = "") -> list[EmpleadoPersonal]:
    query = db.session.query(EmpleadoPersonal)
    est = (estado or "").strip().lower()
    if est in ESTADOS_EMPLEADO:
        query = query.filter(EmpleadoPersonal.estado == est)
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        query = query.filter(
            or_(
                EmpleadoPersonal.legajo.ilike(like),
                EmpleadoPersonal.apellido.ilike(like),
                EmpleadoPersonal.nombre.ilike(like),
                EmpleadoPersonal.dni.ilike(like),
                EmpleadoPersonal.puesto.ilike(like),
            )
        )
    return query.order_by(EmpleadoPersonal.apellido, EmpleadoPersonal.nombre).all()


def get_empleado(empleado_id: int) -> EmpleadoPersonal | None:
    return db.session.get(EmpleadoPersonal, empleado_id)


def save_empleado(
    data: dict[str, Any],
    *,
    empleado_id: int | None = None,
    user_id: int | None = None,
) -> tuple[bool, str, EmpleadoPersonal | None]:
    legajo = (data.get("legajo") or "").strip()
    apellido = (data.get("apellido") or "").strip()
    nombre = (data.get("nombre") or "").strip()
    if not legajo or not apellido or not nombre:
        return False, "Legajo, apellido y nombre son obligatorios.", None

    estado = (data.get("estado") or "activo").strip().lower()
    if estado not in ESTADOS_EMPLEADO:
        estado = "activo"

    existing_legajo = (
        db.session.query(EmpleadoPersonal)
        .filter(EmpleadoPersonal.legajo == legajo)
        .filter(EmpleadoPersonal.id != (empleado_id or -1))
        .first()
    )
    if existing_legajo:
        return False, f"Ya existe un legajo con número {legajo}.", None

    if empleado_id:
        emp = db.session.get(EmpleadoPersonal, empleado_id)
        if emp is None:
            return False, "Empleado no encontrado.", None
    else:
        emp = EmpleadoPersonal(created_by_id=user_id)
        db.session.add(emp)

    emp.legajo = legajo
    emp.dni = (data.get("dni") or "").strip()[:16]
    emp.cuil = (data.get("cuil") or "").strip()[:16]
    emp.apellido = apellido[:128]
    emp.nombre = nombre[:128]
    emp.fecha_nacimiento = parse_iso_date(data.get("fecha_nacimiento"))
    emp.domicilio = (data.get("domicilio") or "").strip()[:256]
    emp.telefono = (data.get("telefono") or "").strip()[:64]
    emp.email = (data.get("email") or "").strip()[:256]
    emp.puesto = (data.get("puesto") or "").strip()[:128]
    emp.area = (data.get("area") or "").strip()[:128]
    emp.fecha_ingreso = parse_iso_date(data.get("fecha_ingreso"))
    emp.estado = estado
    emp.talle_pantalon = (data.get("talle_pantalon") or "").strip()[:16]
    emp.talle_camisa = (data.get("talle_camisa") or "").strip()[:16]
    emp.talle_calzado = (data.get("talle_calzado") or "").strip()[:16]
    emp.talle_guantes = (data.get("talle_guantes") or "").strip()[:16]
    emp.talle_casco = (data.get("talle_casco") or "").strip()[:16]
    emp.observaciones = (data.get("observaciones") or "").strip()[:4000]
    op_raw = (data.get("operador_id") or "").strip()
    emp.operador_id = int(op_raw) if op_raw.isdigit() else None
    emp.updated_by_id = user_id
    db.session.commit()
    return True, "Legajo guardado.", emp


def list_epp_items(*, solo_activos: bool = False) -> list[PersonalEppItem]:
    q = db.session.query(PersonalEppItem).order_by(PersonalEppItem.orden, PersonalEppItem.nombre)
    if solo_activos:
        q = q.filter(PersonalEppItem.activo.is_(True))
    return q.all()


def save_epp_item(
    data: dict[str, Any],
    *,
    item_id: int | None = None,
) -> tuple[bool, str]:
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return False, "El nombre del ítem es obligatorio."
    cat = (data.get("categoria") or "epp").strip().lower()
    if cat not in CATEGORIAS_EPP:
        cat = "epp"
    dup = (
        db.session.query(PersonalEppItem)
        .filter(PersonalEppItem.nombre == nombre)
        .filter(PersonalEppItem.id != (item_id or -1))
        .first()
    )
    if dup:
        return False, "Ya existe un ítem con ese nombre."

    if item_id:
        item = db.session.get(PersonalEppItem, item_id)
        if item is None:
            return False, "Ítem no encontrado."
    else:
        item = PersonalEppItem()
        db.session.add(item)

    item.nombre = nombre[:128]
    item.categoria = cat
    item.requiere_talle = (data.get("requiere_talle") or "") in ("1", "on", "true", "yes")
    item.activo = (data.get("activo") or "1") in ("1", "on", "true", "yes")
    orden_raw = (data.get("orden") or "0").strip()
    item.orden = int(orden_raw) if orden_raw.isdigit() else 0
    db.session.commit()
    return True, "Ítem guardado."


def list_entregas_epp(*, empleado_id: int | None = None, limit: int = 200) -> list[PersonalEntregaEpp]:
    q = (
        db.session.query(PersonalEntregaEpp)
        .join(EmpleadoPersonal)
        .join(PersonalEppItem)
        .order_by(PersonalEntregaEpp.fecha.desc(), PersonalEntregaEpp.id.desc())
    )
    if empleado_id:
        q = q.filter(PersonalEntregaEpp.empleado_id == empleado_id)
    return q.limit(limit).all()


def save_entrega_epp(
    data: dict[str, Any],
    *,
    user_id: int | None = None,
) -> tuple[bool, str]:
    emp_id_raw = (data.get("empleado_id") or "").strip()
    item_id_raw = (data.get("item_id") or "").strip()
    if not emp_id_raw.isdigit() or not item_id_raw.isdigit():
        return False, "Empleado e ítem son obligatorios."
    emp = db.session.get(EmpleadoPersonal, int(emp_id_raw))
    item = db.session.get(PersonalEppItem, int(item_id_raw))
    if emp is None or item is None:
        return False, "Empleado o ítem no encontrado."
    fecha = parse_iso_date(data.get("fecha")) or today_operacion()
    cant_raw = (data.get("cantidad") or "1").strip()
    cantidad = int(cant_raw) if cant_raw.isdigit() and int(cant_raw) > 0 else 1

    entrega = PersonalEntregaEpp(
        empleado_id=emp.id,
        item_id=item.id,
        fecha=fecha,
        talle=(data.get("talle") or "").strip()[:32],
        cantidad=cantidad,
        observaciones=(data.get("observaciones") or "").strip()[:2000],
        created_by_id=user_id,
    )
    db.session.add(entrega)
    db.session.commit()
    return True, "Entrega registrada."


def save_curso(empleado_id: int, data: dict[str, Any]) -> tuple[bool, str]:
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return False, "El nombre del curso es obligatorio."
    emp = db.session.get(EmpleadoPersonal, empleado_id)
    if emp is None:
        return False, "Empleado no encontrado."
    curso_id_raw = (data.get("curso_id") or "").strip()
    if curso_id_raw.isdigit():
        curso = db.session.get(PersonalCurso, int(curso_id_raw))
        if curso is None or curso.empleado_id != empleado_id:
            return False, "Curso no encontrado."
    else:
        curso = PersonalCurso(empleado_id=empleado_id)
        db.session.add(curso)
    curso.nombre = nombre[:256]
    curso.institucion = (data.get("institucion") or "").strip()[:256]
    curso.fecha_realizacion = parse_iso_date(data.get("fecha_realizacion"))
    curso.fecha_vencimiento = parse_iso_date(data.get("fecha_vencimiento"))
    curso.observaciones = (data.get("observaciones") or "").strip()[:2000]
    db.session.commit()
    return True, "Curso guardado."


def save_apercibimiento(empleado_id: int, data: dict[str, Any], *, registrado_por: str = "") -> tuple[bool, str]:
    emp = db.session.get(EmpleadoPersonal, empleado_id)
    if emp is None:
        return False, "Empleado no encontrado."
    fecha = parse_iso_date(data.get("fecha")) or today_operacion()
    tipo = (data.get("tipo") or "escrito").strip().lower()
    if tipo not in TIPOS_APERCIBIMIENTO:
        tipo = "escrito"
    apr_id_raw = (data.get("apercibimiento_id") or "").strip()
    if apr_id_raw.isdigit():
        apr = db.session.get(PersonalApercibimiento, int(apr_id_raw))
        if apr is None or apr.empleado_id != empleado_id:
            return False, "Apercibimiento no encontrado."
    else:
        apr = PersonalApercibimiento(empleado_id=empleado_id)
        db.session.add(apr)
    apr.fecha = fecha
    apr.tipo = tipo
    apr.motivo = (data.get("motivo") or "").strip()[:512]
    apr.descripcion = (data.get("descripcion") or "").strip()[:4000]
    apr.registrado_por = (registrado_por or data.get("registrado_por") or "").strip()[:256]
    db.session.commit()
    return True, "Apercibimiento guardado."


def save_art(empleado_id: int, data: dict[str, Any]) -> tuple[bool, str]:
    emp = db.session.get(EmpleadoPersonal, empleado_id)
    if emp is None:
        return False, "Empleado no encontrado."
    art = emp.art
    if art is None:
        art = PersonalArt(empleado_id=empleado_id)
        db.session.add(art)
    art.aseguradora = (data.get("aseguradora") or "").strip()[:256]
    art.numero_poliza = (data.get("numero_poliza") or "").strip()[:64]
    art.fecha_alta = parse_iso_date(data.get("fecha_alta"))
    art.fecha_baja = parse_iso_date(data.get("fecha_baja"))
    art.observaciones = (data.get("observaciones") or "").strip()[:2000]
    db.session.commit()
    return True, "Datos de ART guardados."


def list_vacaciones(*, estado: str = "", anio: int | None = None, empleado_id: int | None = None) -> list[PersonalVacacion]:
    q = (
        db.session.query(PersonalVacacion)
        .join(EmpleadoPersonal)
        .order_by(PersonalVacacion.fecha_desde.desc(), PersonalVacacion.id.desc())
    )
    est = (estado or "").strip().lower()
    if est in ESTADOS_VACACION:
        q = q.filter(PersonalVacacion.estado == est)
    if anio is not None:
        q = q.filter(PersonalVacacion.anio == anio)
    if empleado_id:
        q = q.filter(PersonalVacacion.empleado_id == empleado_id)
    return q.all()


def save_vacacion(
    data: dict[str, Any],
    *,
    vacacion_id: int | None = None,
) -> tuple[bool, str]:
    emp_id_raw = (data.get("empleado_id") or "").strip()
    if not emp_id_raw.isdigit():
        return False, "Empleado obligatorio."
    emp = db.session.get(EmpleadoPersonal, int(emp_id_raw))
    if emp is None:
        return False, "Empleado no encontrado."
    desde = parse_iso_date(data.get("fecha_desde"))
    hasta = parse_iso_date(data.get("fecha_hasta"))
    if desde is None or hasta is None:
        return False, "Fechas desde y hasta son obligatorias."
    if hasta < desde:
        return False, "La fecha hasta no puede ser anterior a la fecha desde."
    estado = (data.get("estado") or "pendiente").strip().lower()
    if estado not in ESTADOS_VACACION:
        estado = "pendiente"
    anio_raw = (data.get("anio") or "").strip()
    anio = int(anio_raw) if anio_raw.isdigit() else desde.year

    if vacacion_id:
        vac = db.session.get(PersonalVacacion, vacacion_id)
        if vac is None:
            return False, "Vacación no encontrada."
    else:
        vac = PersonalVacacion(empleado_id=emp.id)
        db.session.add(vac)

    vac.empleado_id = emp.id
    vac.fecha_desde = desde
    vac.fecha_hasta = hasta
    vac.dias = _dias_entre(desde, hasta)
    vac.anio = anio
    vac.estado = estado
    vac.observaciones = (data.get("observaciones") or "").strip()[:2000]
    db.session.commit()
    return True, "Vacación guardada."


def marcar_vacacion_tomada(vacacion_id: int) -> tuple[bool, str]:
    vac = db.session.get(PersonalVacacion, vacacion_id)
    if vac is None:
        return False, "Vacación no encontrada."
    vac.estado = "tomada"
    db.session.commit()
    return True, "Vacación marcada como tomada."
