from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    EmpleadoPersonal,
    Operador,
    PersonalApercibimiento,
    PersonalArt,
    PersonalCurso,
    PersonalEntregaEpp,
    PersonalEppItem,
    PersonalVacacion,
    PersonalVacacionConfig,
    PersonalVacacionPeriodo,
    User,
)
from app.user_roles import ROLE_SGI, ROLE_SOLO_LECTURA_TOTAL, normalize_stored_rol
from app.utils.datetime_operacion import now_operacion_naive_local

ROLES_SIN_LEGAJO: frozenset[str] = frozenset({ROLE_SOLO_LECTURA_TOTAL, ROLE_SGI})


def today_operacion() -> date:
    return now_operacion_naive_local().date()

ESTADOS_EMPLEADO = ("activo", "baja")
ESTADOS_VACACION = (
    "solicitada",
    "aprobada",
    "modificada",
    "rechazada",
    "tomada",
    "cancelada",
    "pendiente",
)
ESTADOS_VACACION_RESERVAN_DIAS = frozenset({"solicitada", "aprobada", "modificada", "pendiente", "tomada"})
ESTADOS_VACACION_PENDIENTES_RESPONSABLE = frozenset({"solicitada"})
ESTADOS_VACACION_PENDIENTES_EMPLEADO = frozenset({"modificada", "rechazada"})
ESTADOS_ENTREGA_EPP = ("pendiente", "confirmada")
TIPOS_APERCIBIMIENTO = ("verbal", "escrito")
CATEGORIAS_EPP = ("ropa", "epp", "otro")
CATEGORIAS_EPP_CON_WORKFLOW = frozenset({"ropa", "epp"})

ESTADO_EMPLEADO_LABELS = {"activo": "Activo", "baja": "Baja"}
ESTADO_VACACION_LABELS = {
    "solicitada": "Solicitada",
    "aprobada": "Aprobada",
    "modificada": "Modificada (pendiente tu confirmación)",
    "rechazada": "Rechazada (pendiente tu confirmación)",
    "tomada": "Tomada",
    "cancelada": "Cancelada",
    "pendiente": "Pendiente (legado)",
}
ESTADO_ENTREGA_EPP_LABELS = {"pendiente": "Pendiente confirmación", "confirmada": "Confirmada"}
TIPO_APERCIBIMIENTO_LABELS = {"verbal": "Verbal", "escrito": "Escrito"}
CATEGORIA_EPP_LABELS = {"ropa": "Ropa", "epp": "EPP", "otro": "Otro"}

# Catálogo inicial si aún no hay ítems (ropa y EPP).
DEFAULT_EPP_CATALOG: tuple[tuple[str, str, int, bool], ...] = (
    ("Pantalón", "ropa", 10, True),
    ("Camisa / remera", "ropa", 20, True),
    ("Mameluco", "ropa", 30, True),
    ("Calzado de seguridad", "ropa", 40, True),
    ("Casco", "epp", 50, True),
    ("Guantes", "epp", 60, True),
    ("Anteojos de seguridad", "epp", 70, True),
    ("Protector auricular", "epp", 80, False),
    ("Barbijo", "epp", 90, False),
)

# Campos del legajo RRHH considerados para marcar perfil incompleto.
LEGAJO_COMPLETENESS_FIELDS: tuple[tuple[str, str], ...] = (
    ("dni", "DNI"),
    ("cuil", "CUIL"),
    ("fecha_nacimiento", "Fecha de nacimiento"),
    ("fecha_ingreso", "Fecha de ingreso"),
    ("puesto", "Puesto"),
    ("area", "Área"),
    ("domicilio", "Domicilio"),
    ("telefono", "Teléfono"),
    ("email", "Email"),
    ("talle_pantalon", "Talle pantalón"),
    ("talle_camisa", "Talle camisa"),
    ("talle_calzado", "Talle calzado"),
    ("talle_guantes", "Talle guantes"),
    ("talle_mameluco", "Talle mameluco"),
)


def parse_iso_date(raw: str | None) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def user_requires_legajo(user: User | None) -> bool:
    """Angel y SGI no llevan legajo RRHH."""
    if user is None:
        return False
    return normalize_stored_rol(getattr(user, "rol", None)) not in ROLES_SIN_LEGAJO


def _query_empleados_con_legajo():
    """Empleados visibles en RRHH (excluye usuarios Angel / SGI)."""
    return (
        db.session.query(EmpleadoPersonal)
        .outerjoin(User, EmpleadoPersonal.user_id == User.id)
        .filter(
            or_(
                EmpleadoPersonal.user_id.is_(None),
                User.rol.notin_(tuple(ROLES_SIN_LEGAJO)),
            )
        )
    )


def split_nombre_completo(full: str | None, *, fallback: str = "") -> tuple[str, str]:
    """Devuelve (apellido, nombre) a partir de «Apellido, Nombre» o «Nombre Apellido»."""
    s = (full or "").strip()
    if not s:
        return fallback, ""
    if "," in s:
        ap, nom = [p.strip() for p in s.split(",", 1)]
        return ap or fallback, nom
    parts = s.split(None, 1)
    if len(parts) == 1:
        return fallback, parts[0]
    return parts[1], parts[0]


def format_legajo_correlativo(year: int, seq: int) -> str:
    """Número de legajo: año de ingreso + correlativo de ese año (ej. 2026-003)."""
    return f"{year}-{seq:03d}"


def renumber_legajos_for_year(year: int) -> None:
    """Reasigna correlativos del año según fecha de ingreso (y id como desempate)."""
    rows = (
        _query_empleados_con_legajo()
        .filter(
            EmpleadoPersonal.fecha_ingreso.isnot(None),
            func.extract("year", EmpleadoPersonal.fecha_ingreso) == year,
        )
        .order_by(EmpleadoPersonal.fecha_ingreso.asc(), EmpleadoPersonal.id.asc())
        .all()
    )
    if not rows:
        return
    # Fase temporal: evita choque UNIQUE al reordenar (ej. 2026-002 → 2026-001).
    for emp in rows:
        emp.legajo = f"TMP-R{emp.id}"[:32]
    db.session.flush()
    for seq, emp in enumerate(rows, start=1):
        emp.legajo = format_legajo_correlativo(year, seq)


def normalize_legajos_correlativos() -> None:
    """Fecha de ingreso faltante → hoy; renumerar todos los años con legajos."""
    sin_fecha = _query_empleados_con_legajo().filter(EmpleadoPersonal.fecha_ingreso.is_(None)).all()
    hoy = today_operacion()
    for emp in sin_fecha:
        emp.fecha_ingreso = hoy
    years_raw = (
        db.session.query(func.extract("year", EmpleadoPersonal.fecha_ingreso))
        .filter(EmpleadoPersonal.fecha_ingreso.isnot(None))
        .distinct()
        .all()
    )
    for (year_val,) in years_raw:
        if year_val is not None:
            renumber_legajos_for_year(int(year_val))


def _temp_legajo_for_user(user: User) -> str:
    return f"TMP-U{user.id}"[:32]


def _find_orphan_legajo_for_user(user: User) -> EmpleadoPersonal | None:
    """Legajo sin user_id que corresponde al usuario (evita duplicados tras migración)."""
    username = (user.username or "").strip().lower()
    if username:
        by_legajo = (
            db.session.query(EmpleadoPersonal)
            .filter(
                EmpleadoPersonal.user_id.is_(None),
                func.lower(EmpleadoPersonal.legajo) == username,
            )
            .first()
        )
        if by_legajo is not None:
            return by_legajo

    apellido, nombre = split_nombre_completo(user.nombre_completo, fallback=user.username or "")
    if apellido and nombre:
        by_name = (
            db.session.query(EmpleadoPersonal)
            .filter(
                EmpleadoPersonal.user_id.is_(None),
                func.lower(EmpleadoPersonal.apellido) == apellido.lower(),
                func.lower(EmpleadoPersonal.nombre) == nombre.lower(),
            )
            .first()
        )
        if by_name is not None:
            return by_name

    op_names = {n for n in {username, (user.nombre_completo or "").strip().lower()} if n}
    if not op_names:
        return None
    ops = db.session.query(Operador).filter(func.lower(Operador.nombre).in_(tuple(op_names))).all()
    for op in ops:
        emp = (
            db.session.query(EmpleadoPersonal)
            .filter(
                EmpleadoPersonal.user_id.is_(None),
                EmpleadoPersonal.operador_id == op.id,
            )
            .first()
        )
        if emp is not None:
            return emp
    return None


def ensure_empleado_for_user(user: User, *, commit: bool = True) -> EmpleadoPersonal | None:
    """Crea el legajo RRHH para un usuario si aún no existe."""
    if not user_requires_legajo(user):
        return None
    existing = (
        db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == user.id).first()
    )
    if existing is not None:
        return existing

    orphan = _find_orphan_legajo_for_user(user)
    if orphan is not None:
        orphan.user_id = user.id
        if commit:
            db.session.commit()
        return orphan

    apellido, nombre = split_nombre_completo(user.nombre_completo, fallback=user.username or "Sin nombre")
    emp = EmpleadoPersonal(
        user_id=user.id,
        legajo=_temp_legajo_for_user(user),
        apellido=apellido[:128],
        nombre=nombre[:128],
        fecha_ingreso=today_operacion(),
        estado="activo" if user.activo else "baja",
    )
    db.session.add(emp)
    db.session.flush()
    renumber_legajos_for_year(emp.fecha_ingreso.year)
    if commit:
        db.session.commit()
    return emp


def sync_empleados_from_users() -> None:
    """Asegura un legajo por cada usuario que lo requiere (idempotente)."""
    linked_ids = {
        uid
        for (uid,) in db.session.query(EmpleadoPersonal.user_id)
        .filter(EmpleadoPersonal.user_id.isnot(None))
        .all()
        if uid is not None
    }
    users = db.session.scalars(select(User)).all()
    changed = False
    for user in users:
        if not user_requires_legajo(user):
            emp = get_empleado_by_user_id(user.id)
            if emp is not None:
                db.session.delete(emp)
                changed = True
            continue
        if user.id not in linked_ids:
            ensure_empleado_for_user(user, commit=False)
            changed = True
    if changed:
        db.session.commit()
    normalize_legajos_correlativos()
    db.session.commit()


def get_empleado_by_user_id(user_id: int) -> EmpleadoPersonal | None:
    return db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == user_id).first()


def sync_user_nombre_from_empleado(emp: EmpleadoPersonal) -> None:
    if emp.user_id is None:
        return
    user = db.session.get(User, emp.user_id)
    if user is None:
        return
    user.nombre_completo = emp.nombre_completo


def sync_empleado_for_user_role(user: User) -> None:
    """Crea, actualiza o elimina el legajo según el perfil del usuario."""
    if not user_requires_legajo(user):
        emp = get_empleado_by_user_id(user.id)
        if emp is not None:
            db.session.delete(emp)
        return
    emp = get_empleado_by_user_id(user.id)
    if emp is None:
        ensure_empleado_for_user(user, commit=False)
        return
    apellido, nombre = split_nombre_completo(user.nombre_completo, fallback=user.username or emp.apellido)
    if apellido:
        emp.apellido = apellido[:128]
    if nombre:
        emp.nombre = nombre[:128]
    emp.estado = "activo" if user.activo else "baja"


def sync_empleado_nombre_from_user(user: User) -> None:
    sync_empleado_for_user_role(user)


def legajo_missing_fields(emp: EmpleadoPersonal) -> list[str]:
    missing: list[str] = []
    for attr, label in LEGAJO_COMPLETENESS_FIELDS:
        val = getattr(emp, attr, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(label)
    return missing


def legajo_is_complete(emp: EmpleadoPersonal) -> bool:
    return not legajo_missing_fields(emp)


def legajo_status_for_empleado(emp: EmpleadoPersonal | None) -> dict[str, Any]:
    if emp is None:
        return {
            "empleado_id": None,
            "complete": False,
            "missing": ["Sin legajo"],
            "missing_count": 0,
        }
    missing = legajo_missing_fields(emp)
    return {
        "empleado_id": emp.id,
        "complete": not missing,
        "missing": missing,
        "missing_count": len(missing),
    }


def legajo_status_by_user_id(*, sync_users: bool = True) -> dict[int, dict[str, Any]]:
    """Mapa user_id → estado de completitud del legajo RRHH."""
    if sync_users:
        sync_empleados_from_users()
    rows = (
        db.session.query(EmpleadoPersonal)
        .join(User, EmpleadoPersonal.user_id == User.id)
        .filter(~User.rol.in_(tuple(ROLES_SIN_LEGAJO)))
        .all()
    )
    return {int(emp.user_id): legajo_status_for_empleado(emp) for emp in rows if emp.user_id is not None}


def legajo_status_by_empleado_id(*, sync_users: bool = True) -> dict[int, dict[str, Any]]:
    if sync_users:
        sync_empleados_from_users()
    rows = _query_empleados_con_legajo().all()
    return {int(emp.id): legajo_status_for_empleado(emp) for emp in rows}


def _dias_entre(desde: date, hasta: date) -> int:
    return max(1, (hasta - desde).days + 1)


def dashboard_counts() -> dict[str, int]:
    hoy = today_operacion()
    base = _query_empleados_con_legajo()

    activos = base.filter(EmpleadoPersonal.estado == "activo").count()
    cumple_mes = base.filter(
        EmpleadoPersonal.estado == "activo",
        EmpleadoPersonal.fecha_nacimiento.isnot(None),
        func.extract("month", EmpleadoPersonal.fecha_nacimiento) == hoy.month,
    ).count()
    cursos_por_vencer = (
        db.session.query(func.count(PersonalCurso.id))
        .join(EmpleadoPersonal)
        .outerjoin(User, EmpleadoPersonal.user_id == User.id)
        .filter(
            or_(
                EmpleadoPersonal.user_id.is_(None),
                User.rol.notin_(tuple(ROLES_SIN_LEGAJO)),
            ),
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
        .filter(PersonalVacacion.estado.in_(tuple(ESTADOS_VACACION_PENDIENTES_RESPONSABLE)))
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


def es_cumpleanos_hoy(fecha_nac: date | None, hoy: date | None = None) -> bool:
    """True si hoy es el cumpleaños (29/02 se festeja el 28/02 en años no bisiestos)."""
    if fecha_nac is None:
        return False
    hoy = hoy or today_operacion()
    if fecha_nac.month == hoy.month and fecha_nac.day == hoy.day:
        return True
    if fecha_nac.month == 2 and fecha_nac.day == 29 and hoy.month == 2 and hoy.day == 28:
        try:
            date(hoy.year, 2, 29)
        except ValueError:
            return True
    return False


def cumpleanos_hoy() -> list[EmpleadoPersonal]:
    """Empleados activos que cumplen años hoy."""
    hoy = today_operacion()
    empleados = (
        _query_empleados_con_legajo()
        .filter(EmpleadoPersonal.estado == "activo", EmpleadoPersonal.fecha_nacimiento.isnot(None))
        .order_by(EmpleadoPersonal.apellido, EmpleadoPersonal.nombre)
        .all()
    )
    return [e for e in empleados if es_cumpleanos_hoy(e.fecha_nacimiento, hoy)]


def proximos_cumpleanos(dias: int = 30) -> list[EmpleadoPersonal]:
    hoy = today_operacion()
    empleados = (
        _query_empleados_con_legajo()
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
    sync_empleados_from_users()
    query = _query_empleados_con_legajo()
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
                User.username.ilike(like),
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
    apellido = (data.get("apellido") or "").strip()
    nombre = (data.get("nombre") or "").strip()
    if not apellido or not nombre:
        return False, "Apellido y nombre son obligatorios.", None

    fecha_ingreso = parse_iso_date(data.get("fecha_ingreso"))
    if fecha_ingreso is None:
        return False, "La fecha de ingreso es obligatoria (define el número de legajo).", None

    estado = (data.get("estado") or "activo").strip().lower()
    if estado not in ESTADOS_EMPLEADO:
        estado = "activo"

    if empleado_id:
        emp = db.session.get(EmpleadoPersonal, empleado_id)
        if emp is None:
            return False, "Empleado no encontrado.", None
    else:
        return False, "Los legajos se crean al dar de alta un usuario en Administración.", None

    old_year = emp.fecha_ingreso.year if emp.fecha_ingreso else None

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
    emp.fecha_ingreso = fecha_ingreso
    emp.estado = estado
    emp.talle_pantalon = (data.get("talle_pantalon") or "").strip()[:16]
    emp.talle_camisa = (data.get("talle_camisa") or "").strip()[:16]
    emp.talle_calzado = (data.get("talle_calzado") or "").strip()[:16]
    emp.talle_guantes = (data.get("talle_guantes") or "").strip()[:16]
    emp.talle_mameluco = (data.get("talle_mameluco") or "").strip()[:16]
    emp.observaciones = (data.get("observaciones") or "").strip()[:4000]
    op_raw = (data.get("operador_id") or "").strip()
    emp.operador_id = int(op_raw) if op_raw.isdigit() else None
    emp.updated_by_id = user_id
    db.session.flush()
    renumber_legajos_for_year(fecha_ingreso.year)
    if old_year is not None and old_year != fecha_ingreso.year:
        renumber_legajos_for_year(old_year)
    sync_user_nombre_from_empleado(emp)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, "No se pudo guardar el legajo (conflicto de datos). Revisá el número de legajo o contactá al administrador.", None
    return True, "Legajo guardado.", emp


def list_epp_items(*, solo_activos: bool = False) -> list[PersonalEppItem]:
    q = db.session.query(PersonalEppItem).order_by(PersonalEppItem.orden, PersonalEppItem.nombre)
    if solo_activos:
        q = q.filter(PersonalEppItem.activo.is_(True))
    return q.all()


def ensure_default_epp_catalog() -> int:
    """Crea ítems base de ropa y EPP si el catálogo está vacío."""
    total = int(db.session.query(func.count(PersonalEppItem.id)).scalar() or 0)
    if total > 0:
        return 0
    for nombre, cat, orden, req_talle in DEFAULT_EPP_CATALOG:
        db.session.add(
            PersonalEppItem(
                nombre=nombre,
                categoria=cat,
                orden=orden,
                requiere_talle=req_talle,
                activo=True,
            )
        )
    db.session.commit()
    return len(DEFAULT_EPP_CATALOG)


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


def item_epp_requiere_workflow(item: PersonalEppItem | None) -> bool:
    if item is None:
        return False
    return (item.categoria or "").strip().lower() in CATEGORIAS_EPP_CON_WORKFLOW


def ultima_entrega_confirmada_empleado_item(empleado_id: int, item_id: int) -> PersonalEntregaEpp | None:
    return (
        db.session.query(PersonalEntregaEpp)
        .filter(
            PersonalEntregaEpp.empleado_id == empleado_id,
            PersonalEntregaEpp.item_id == item_id,
            PersonalEntregaEpp.estado == "confirmada",
        )
        .order_by(PersonalEntregaEpp.fecha.desc(), PersonalEntregaEpp.id.desc())
        .first()
    )


def entrega_epp_pendiente_empleado_item(empleado_id: int, item_id: int) -> PersonalEntregaEpp | None:
    return (
        db.session.query(PersonalEntregaEpp)
        .filter(
            PersonalEntregaEpp.empleado_id == empleado_id,
            PersonalEntregaEpp.item_id == item_id,
            PersonalEntregaEpp.estado == "pendiente",
        )
        .order_by(PersonalEntregaEpp.fecha.desc(), PersonalEntregaEpp.id.desc())
        .first()
    )


def list_entregas_epp_pendientes_empleado(empleado_id: int) -> list[PersonalEntregaEpp]:
    return (
        db.session.query(PersonalEntregaEpp)
        .join(PersonalEppItem)
        .filter(
            PersonalEntregaEpp.empleado_id == empleado_id,
            PersonalEntregaEpp.estado == "pendiente",
        )
        .order_by(PersonalEntregaEpp.fecha.desc(), PersonalEntregaEpp.id.desc())
        .all()
    )


def entrega_epp_puede_confirmar_usuario(entrega: PersonalEntregaEpp | None, *, user_id: int) -> tuple[bool, str]:
    """Indica si el empleado titular puede confirmar la entrega y el motivo si no."""
    if entrega is None:
        return False, "Entrega no encontrada."
    if entrega.estado != "pendiente":
        return False, "Esta entrega ya fue confirmada."
    emp = entrega.empleado
    if emp is None:
        return False, "No se encontró el legajo asociado a esta entrega."
    if emp.user_id is None:
        return (
            False,
            "Tu legajo no está vinculado a tu usuario. Pedí a RRHH que revise el legajo en Personal.",
        )
    if int(emp.user_id) != int(user_id):
        return False, "Solo el empleado titular puede confirmar esta entrega."
    if not item_epp_requiere_workflow(entrega.item):
        return False, "Esta entrega no requiere confirmación del empleado."
    if entrega.prenda_anterior_entrega_id is not None and not entrega.prenda_anterior_devuelta:
        return (
            False,
            "RRHH debe registrar la devolución de la prenda anterior antes de que puedas confirmar.",
        )
    return True, ""


def count_entregas_epp_pendientes_usuario(user_id: int) -> int:
    emp = get_empleado_by_user_id(user_id)
    if emp is None:
        return 0
    return int(
        db.session.query(func.count(PersonalEntregaEpp.id))
        .filter(
            PersonalEntregaEpp.empleado_id == emp.id,
            PersonalEntregaEpp.estado == "pendiente",
        )
        .scalar()
        or 0
    )


def count_vacaciones_pendientes_empleado(user_id: int) -> int:
    emp = get_empleado_by_user_id(user_id)
    if emp is None:
        return 0
    return int(
        db.session.query(func.count(PersonalVacacion.id))
        .filter(
            PersonalVacacion.empleado_id == emp.id,
            PersonalVacacion.estado.in_(tuple(ESTADOS_VACACION_PENDIENTES_EMPLEADO)),
        )
        .scalar()
        or 0
    )


def _checkbox_truthy(raw: str | None) -> bool:
    return (raw or "") in ("1", "on", "true", "yes")


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

    requiere_workflow = item_epp_requiere_workflow(item)
    if requiere_workflow:
        pendiente = entrega_epp_pendiente_empleado_item(emp.id, item.id)
        if pendiente is not None:
            return (
                False,
                "Hay una entrega pendiente de confirmación para este ítem. "
                "El empleado debe confirmarla desde su usuario antes de registrar otra.",
            )
    anterior = ultima_entrega_confirmada_empleado_item(emp.id, item.id) if requiere_workflow else None
    prenda_devuelta = _checkbox_truthy(data.get("prenda_anterior_devuelta"))
    if anterior is not None and not prenda_devuelta:
        return (
            False,
            f"Debe registrarse la devolución de la prenda anterior ({anterior.item.nombre}, "
            f"entrega del {anterior.fecha.strftime('%d/%m/%Y')}).",
        )

    if requiere_workflow:
        estado = "pendiente"
        confirmada_at = None
        confirmada_by = None
    else:
        estado = "confirmada"
        confirmada_at = datetime.now(timezone.utc)
        confirmada_by = user_id

    entrega = PersonalEntregaEpp(
        empleado_id=emp.id,
        item_id=item.id,
        fecha=fecha,
        talle=(data.get("talle") or "").strip()[:32],
        cantidad=cantidad,
        observaciones=(data.get("observaciones") or "").strip()[:2000],
        estado=estado,
        prenda_anterior_devuelta=prenda_devuelta,
        prenda_anterior_entrega_id=anterior.id if anterior is not None else None,
        confirmada_at=confirmada_at,
        confirmada_by_user_id=confirmada_by,
        created_by_id=user_id,
    )
    db.session.add(entrega)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        err = str(exc).lower()
        if "estado" in err or "personal_entregas_epp" in err:
            return (
                False,
                "No se pudo guardar la entrega. Ejecutá «flask db upgrade» en el servidor para aplicar las migraciones de Personal.",
            )
        return False, "No se pudo guardar la entrega. Revisá los datos o contactá al administrador."
    if requiere_workflow:
        from app.services.personal_epp_reminder_service import maybe_notify_entrega_epp_pendiente

        mail_ok, mail_detail = maybe_notify_entrega_epp_pendiente(entrega)
        base_msg = "Entrega registrada. El empleado debe confirmarla desde su usuario."
        if not mail_ok and mail_detail:
            return True, f"{base_msg} Aviso por correo: {mail_detail}"
        return True, base_msg
    return True, "Entrega registrada."


def confirmar_entrega_epp(entrega_id: int, *, user_id: int) -> tuple[bool, str]:
    entrega = db.session.get(PersonalEntregaEpp, entrega_id)
    puede, motivo = entrega_epp_puede_confirmar_usuario(entrega, user_id=user_id)
    if not puede:
        return False, motivo

    entrega.estado = "confirmada"
    entrega.confirmada_at = datetime.now(timezone.utc)
    entrega.confirmada_by_user_id = user_id
    db.session.commit()
    return True, "Entrega confirmada."


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


def list_vacaciones(
    *,
    estado: str = "",
    anio: int | None = None,
    empleado_id: int | None = None,
    pendientes_responsable: bool = False,
    pendientes_empleado_id: int | None = None,
) -> list[PersonalVacacion]:
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
    if pendientes_responsable:
        q = q.filter(PersonalVacacion.estado.in_(tuple(ESTADOS_VACACION_PENDIENTES_RESPONSABLE)))
    if pendientes_empleado_id:
        q = q.filter(
            PersonalVacacion.empleado_id == pendientes_empleado_id,
            PersonalVacacion.estado.in_(tuple(ESTADOS_VACACION_PENDIENTES_EMPLEADO)),
        )
    return q.all()


def get_vacacion_config() -> PersonalVacacionConfig:
    row = db.session.get(PersonalVacacionConfig, 1)
    if row is None:
        row = PersonalVacacionConfig(id=1)
        db.session.add(row)
        db.session.commit()
    return row


def set_responsable_vacaciones(
    user_id: int | None,
    *,
    by_user_id: int | None,
    email: str | None = None,
) -> tuple[bool, str]:
    from app.services.deadline_alert_email_service import normalize_validate_email
    from app.services.personal_epp_reminder_service import resolve_empleado_email

    cfg = get_vacacion_config()
    if user_id is not None:
        u = db.session.get(User, user_id)
        if u is None or not u.activo:
            return False, "Usuario responsable no válido."
        emp = get_empleado_by_user_id(user_id)
        legajo_mail = resolve_empleado_email(emp) if emp is not None else None
        mail = normalize_validate_email((email or "").strip()) or legajo_mail
        if not mail and not user_requires_legajo(u):
            return False, "Indicá un email de contacto para el responsable (perfil Angel / sin legajo)."
        cfg.responsable_user_id = user_id
        cfg.responsable_email = mail or ""
    else:
        cfg.responsable_user_id = None
        cfg.responsable_email = ""
    cfg.updated_by_id = by_user_id
    cfg.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return True, "Responsable de vacaciones actualizado."


def user_is_responsable_vacaciones(user: User | None) -> bool:
    if user is None or not user.activo:
        return False
    cfg = get_vacacion_config()
    return cfg.responsable_user_id is not None and int(cfg.responsable_user_id) == int(user.id)


def list_vacacion_periodos(*, empleado_id: int | None = None, anio: int | None = None) -> list[PersonalVacacionPeriodo]:
    q = db.session.query(PersonalVacacionPeriodo).join(EmpleadoPersonal).order_by(
        PersonalVacacionPeriodo.anio.desc(), EmpleadoPersonal.apellido, EmpleadoPersonal.nombre
    )
    if empleado_id:
        q = q.filter(PersonalVacacionPeriodo.empleado_id == empleado_id)
    if anio is not None:
        q = q.filter(PersonalVacacionPeriodo.anio == anio)
    return q.all()


def _dias_usados_periodo(empleado_id: int, anio: int, *, excluir_vacacion_id: int | None = None) -> int:
    q = db.session.query(func.coalesce(func.sum(PersonalVacacion.dias), 0)).filter(
        PersonalVacacion.empleado_id == empleado_id,
        PersonalVacacion.anio == anio,
        PersonalVacacion.estado.in_(tuple(ESTADOS_VACACION_RESERVAN_DIAS)),
    )
    if excluir_vacacion_id:
        q = q.filter(PersonalVacacion.id != excluir_vacacion_id)
    return int(q.scalar() or 0)


def saldo_vacacion_periodo(empleado_id: int, anio: int, *, excluir_vacacion_id: int | None = None) -> dict[str, int]:
    periodo = (
        db.session.query(PersonalVacacionPeriodo)
        .filter(PersonalVacacionPeriodo.empleado_id == empleado_id, PersonalVacacionPeriodo.anio == anio)
        .one_or_none()
    )
    asignados = int(periodo.dias_asignados) if periodo else 0
    usados = _dias_usados_periodo(empleado_id, anio, excluir_vacacion_id=excluir_vacacion_id)
    return {"asignados": asignados, "usados": usados, "disponibles": max(0, asignados - usados)}


def saldos_vacaciones_empleado(empleado_id: int) -> list[dict[str, Any]]:
    periodos = list_vacacion_periodos(empleado_id=empleado_id)
    out: list[dict[str, Any]] = []
    for p in periodos:
        saldo = saldo_vacacion_periodo(empleado_id, p.anio)
        out.append(
            {
                "periodo": p,
                "anio": p.anio,
                "asignados": saldo["asignados"],
                "usados": saldo["usados"],
                "disponibles": saldo["disponibles"],
            }
        )
    return out


def _resolve_dias_asignados_periodo(
    empleado_id: int,
    anio: int,
    data: dict[str, Any],
) -> tuple[int | None, str | None]:
    """Interpreta días disponibles o asignados totales para un período."""
    usados = _dias_usados_periodo(empleado_id, anio)
    disp_raw = (data.get("dias_disponibles") or "").strip()
    asig_raw = (data.get("dias_asignados") or "").strip()
    mode = (data.get("input_mode") or "").strip().lower()

    if disp_raw or mode == "disponibles":
        if not disp_raw.isdigit():
            return None, "Días disponibles obligatorios."
        disponibles = int(disp_raw)
        if disponibles < 0:
            return None, "Los días disponibles no pueden ser negativos."
        return disponibles + usados, None

    if not asig_raw.isdigit():
        return None, "Días asignados obligatorios."
    dias = int(asig_raw)
    if dias < 0:
        return None, "Los días asignados no pueden ser negativos."
    if dias < usados:
        return None, f"No podés asignar menos de {usados} días (ya hay solicitudes/aprobaciones por ese período)."
    return dias, None


def save_vacacion_periodo(data: dict[str, Any], *, user_id: int | None) -> tuple[bool, str]:
    emp_id_raw = (data.get("empleado_id") or "").strip()
    anio_raw = (data.get("anio") or "").strip()
    if not emp_id_raw.isdigit():
        return False, "Empleado obligatorio."
    if not anio_raw.isdigit():
        return False, "Año del período obligatorio."
    emp = db.session.get(EmpleadoPersonal, int(emp_id_raw))
    if emp is None:
        return False, "Empleado no encontrado."
    anio = int(anio_raw)
    dias, err = _resolve_dias_asignados_periodo(emp.id, anio, data)
    if err is not None or dias is None:
        return False, err or "Días del período no válidos."

    periodo_id_raw = (data.get("periodo_id") or "").strip()
    periodo: PersonalVacacionPeriodo | None = None
    if periodo_id_raw.isdigit():
        periodo = db.session.get(PersonalVacacionPeriodo, int(periodo_id_raw))
    if periodo is None:
        periodo = (
            db.session.query(PersonalVacacionPeriodo)
            .filter(PersonalVacacionPeriodo.empleado_id == emp.id, PersonalVacacionPeriodo.anio == anio)
            .one_or_none()
        )
    if periodo is None:
        periodo = PersonalVacacionPeriodo(empleado_id=emp.id, anio=anio, created_by_id=user_id)
        db.session.add(periodo)
    periodo.dias_asignados = dias
    periodo.observaciones = (data.get("observaciones") or "").strip()[:2000]
    periodo.updated_by_id = user_id
    db.session.commit()
    return True, "Período de vacaciones guardado."


def save_vacacion_periodo_masivo(
    data: dict[str, Any],
    *,
    user_id: int | None,
    empleado_ids: list[str] | None = None,
) -> tuple[bool, str, int]:
    """Asigna el mismo saldo de días a todos los empleados activos (o a los seleccionados)."""
    anio_raw = (data.get("anio") or "").strip()
    disp_raw = (data.get("dias_disponibles") or "").strip()
    dias_raw = (data.get("dias_asignados") or "").strip()
    mode = (data.get("input_mode") or "").strip().lower()
    if not anio_raw.isdigit():
        return False, "Año del período obligatorio.", 0
    if not disp_raw.isdigit() and not dias_raw.isdigit():
        return False, "Días del período obligatorios.", 0
    anio = int(anio_raw)
    if disp_raw.isdigit() or mode == "disponibles":
        if not disp_raw.isdigit():
            return False, "Días disponibles obligatorios.", 0
        if int(disp_raw) < 0:
            return False, "Los días disponibles no pueden ser negativos.", 0
        dias_key, dias_val = "dias_disponibles", disp_raw
        resumen = f"{int(disp_raw)} días disponibles"
    else:
        if int(dias_raw) < 0:
            return False, "Los días asignados no pueden ser negativos.", 0
        dias_key, dias_val = "dias_asignados", dias_raw
        resumen = f"{int(dias_raw)} días asignados"

    empleados = list_empleados(estado="activo")
    if empleado_ids:
        ids = {int(x) for x in empleado_ids if str(x).isdigit()}
        empleados = [e for e in empleados if e.id in ids]
    if not empleados:
        return False, "No hay empleados activos para cargar el período.", 0

    ok_count = 0
    errores: list[str] = []
    for emp in empleados:
        ok, msg = save_vacacion_periodo(
            {
                "empleado_id": str(emp.id),
                "anio": str(anio),
                dias_key: dias_val,
                "input_mode": mode,
                "observaciones": (data.get("observaciones") or "").strip(),
            },
            user_id=user_id,
        )
        if ok:
            ok_count += 1
        else:
            errores.append(f"{emp.nombre_completo}: {msg}")

    if ok_count == 0:
        detalle = errores[0] if errores else "Sin cambios."
        return False, f"No se pudo cargar ningún período. {detalle}", 0
    if errores:
        return True, f"Período {anio} cargado para {ok_count} empleado(s). {len(errores)} con error.", ok_count
    return True, f"Período {anio}: {resumen} para {ok_count} empleado(s).", ok_count


def periodo_lote_filas(empleados: list[EmpleadoPersonal], anio: int) -> list[dict[str, Any]]:
    """Filas para la tabla de carga en lote (días ya cargados por empleado)."""
    periodos_by_emp = {int(p.empleado_id): p for p in list_vacacion_periodos(anio=anio)}
    rows: list[dict[str, Any]] = []
    for emp in empleados:
        periodo = periodos_by_emp.get(int(emp.id))
        saldo = saldo_vacacion_periodo(int(emp.id), anio)
        rows.append(
            {
                "empleado": emp,
                "dias_asignados": int(periodo.dias_asignados) if periodo is not None else "",
                "dias_disponibles": saldo["disponibles"] if periodo is not None else "",
                "usados": saldo["usados"],
                "periodo_id": int(periodo.id) if periodo is not None else None,
            }
        )
    return rows


def save_vacacion_periodo_lote(
    *,
    anio: int,
    empleado_ids: list[str],
    dias_values: list[str],
    user_id: int | None,
    observaciones: str = "",
    input_mode: str = "disponibles",
) -> tuple[bool, str, int]:
    """Guarda días por período desde la tabla en lote (omite filas vacías)."""
    if anio < 2000 or anio > 2100:
        return False, "Año del período no válido.", 0
    if len(empleado_ids) != len(dias_values):
        return False, "Datos de la tabla incompletos.", 0

    mode = (input_mode or "disponibles").strip().lower()
    dias_key = "dias_disponibles" if mode == "disponibles" else "dias_asignados"

    ok_count = 0
    errores: list[str] = []
    obs = (observaciones or "").strip()[:2000]
    for emp_id_raw, dias_raw in zip(empleado_ids, dias_values, strict=True):
        dias_s = (dias_raw or "").strip()
        if not dias_s:
            continue
        if not emp_id_raw.isdigit() or not dias_s.isdigit():
            errores.append(f"Fila inválida (empleado {emp_id_raw}).")
            continue
        emp = db.session.get(EmpleadoPersonal, int(emp_id_raw))
        if emp is None:
            errores.append(f"Empleado id {emp_id_raw} no encontrado.")
            continue
        ok, msg = save_vacacion_periodo(
            {
                "empleado_id": emp_id_raw,
                "anio": str(anio),
                dias_key: dias_s,
                "input_mode": mode,
                "observaciones": obs,
            },
            user_id=user_id,
        )
        if ok:
            ok_count += 1
        else:
            errores.append(f"{emp.nombre_completo}: {msg}")

    if ok_count == 0:
        detalle = errores[0] if errores else "No ingresaste días en ninguna fila."
        return False, detalle, 0
    if errores:
        return True, f"Guardado para {ok_count} empleado(s). {len(errores)} fila(s) con error.", ok_count
    return True, f"Período {anio} guardado para {ok_count} empleado(s).", ok_count


def _get_periodo_empleado(empleado_id: int, anio: int) -> PersonalVacacionPeriodo | None:
    return (
        db.session.query(PersonalVacacionPeriodo)
        .filter(PersonalVacacionPeriodo.empleado_id == empleado_id, PersonalVacacionPeriodo.anio == anio)
        .one_or_none()
    )


def solicitar_vacacion(
    empleado_id: int,
    *,
    user_id: int,
    data: dict[str, Any],
) -> tuple[bool, str, PersonalVacacion | None]:
    emp = db.session.get(EmpleadoPersonal, empleado_id)
    if emp is None:
        return False, "Legajo no encontrado.", None
    desde = parse_iso_date(data.get("fecha_desde"))
    hasta = parse_iso_date(data.get("fecha_hasta"))
    if desde is None or hasta is None:
        return False, "Fechas desde y hasta son obligatorias.", None
    if hasta < desde:
        return False, "La fecha hasta no puede ser anterior a la fecha desde.", None
    anio_raw = (data.get("anio") or "").strip()
    anio = int(anio_raw) if anio_raw.isdigit() else desde.year
    periodo = _get_periodo_empleado(empleado_id, anio)
    if periodo is None or int(periodo.dias_asignados) <= 0:
        nombre = emp.nombre_completo
        return False, f"{nombre} no tiene días cargados para el período {anio}. El administrador debe asignarlos primero.", None
    dias = _dias_entre(desde, hasta)
    saldo = saldo_vacacion_periodo(empleado_id, anio)
    if dias > saldo["disponibles"]:
        return (
            False,
            f"Pedís {dias} días pero solo tenés {saldo['disponibles']} disponibles en el período {anio}.",
            None,
        )

    vac = PersonalVacacion(
        empleado_id=empleado_id,
        periodo_id=periodo.id,
        fecha_desde=desde,
        fecha_hasta=hasta,
        dias=dias,
        anio=anio,
        estado="solicitada",
        observaciones=(data.get("observaciones") or "").strip()[:2000],
        solicitada_by_user_id=user_id,
    )
    db.session.add(vac)
    db.session.commit()
    return True, "Solicitud de vacaciones enviada.", vac


def gestionar_vacacion_responsable(
    vacacion_id: int,
    *,
    user_id: int,
    accion: str,
    data: dict[str, Any],
) -> tuple[bool, str, PersonalVacacion | None]:
    vac = db.session.get(PersonalVacacion, vacacion_id)
    if vac is None:
        return False, "Solicitud no encontrada.", None
    if (vac.estado or "").strip() not in ESTADOS_VACACION_PENDIENTES_RESPONSABLE:
        return False, "Esta solicitud ya fue gestionada.", None

    acc = (accion or "").strip().lower()
    now = datetime.now(timezone.utc)
    motivo = (data.get("motivo_responsable") or "").strip()[:2000]

    if acc == "aprobar":
        vac.estado = "aprobada"
        vac.motivo_responsable = motivo
        vac.gestionada_by_user_id = user_id
        vac.gestionada_at = now
        db.session.commit()
        return True, "Vacaciones aprobadas.", vac

    if acc == "rechazar":
        if not motivo:
            return False, "Indicá el motivo del rechazo.", None
        vac.estado = "rechazada"
        vac.motivo_responsable = motivo
        vac.gestionada_by_user_id = user_id
        vac.gestionada_at = now
        db.session.commit()
        return True, "Vacaciones rechazadas. El empleado debe confirmar.", vac

    if acc == "modificar":
        desde = parse_iso_date(data.get("fecha_desde"))
        hasta = parse_iso_date(data.get("fecha_hasta"))
        if desde is None or hasta is None:
            return False, "Indicá las fechas propuestas.", None
        if hasta < desde:
            return False, "La fecha hasta no puede ser anterior a la fecha desde.", None
        dias = _dias_entre(desde, hasta)
        saldo = saldo_vacacion_periodo(vac.empleado_id, vac.anio, excluir_vacacion_id=vac.id)
        if dias > saldo["disponibles"] + vac.dias:
            return (
                False,
                f"La propuesta usa {dias} días pero solo quedan {saldo['disponibles']} disponibles en el período.",
                None,
            )
        vac.fecha_desde_original = vac.fecha_desde
        vac.fecha_hasta_original = vac.fecha_hasta
        vac.fecha_desde = desde
        vac.fecha_hasta = hasta
        vac.dias = dias
        vac.estado = "modificada"
        vac.motivo_responsable = motivo
        vac.gestionada_by_user_id = user_id
        vac.gestionada_at = now
        db.session.commit()
        return True, "Propuesta enviada al empleado para confirmación.", vac

    return False, "Acción no reconocida.", None


def confirmar_vacacion_empleado(
    vacacion_id: int,
    *,
    empleado_id: int,
    user_id: int,
) -> tuple[bool, str, PersonalVacacion | None]:
    vac = db.session.get(PersonalVacacion, vacacion_id)
    if vac is None or int(vac.empleado_id) != int(empleado_id):
        return False, "Solicitud no encontrada.", None
    estado = (vac.estado or "").strip()
    if estado not in ESTADOS_VACACION_PENDIENTES_EMPLEADO:
        return False, "No hay nada pendiente de tu confirmación.", None

    now = datetime.now(timezone.utc)
    if estado == "modificada":
        vac.estado = "aprobada"
        vac.confirmada_empleado_at = now
        db.session.commit()
        return True, "Aceptaste las fechas propuestas. Vacaciones aprobadas.", vac

    if estado == "rechazada":
        vac.estado = "cancelada"
        vac.confirmada_empleado_at = now
        db.session.commit()
        return True, "Rechazo confirmado.", vac

    return False, "Estado no válido.", None


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
    estado = (data.get("estado") or "aprobada").strip().lower()
    if estado not in ESTADOS_VACACION:
        estado = "aprobada"
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
    if (vac.estado or "").strip() not in ("aprobada", "pendiente"):
        return False, "Solo se pueden marcar como tomadas las vacaciones aprobadas."
    vac.estado = "tomada"
    db.session.commit()
    return True, "Vacación marcada como tomada."
