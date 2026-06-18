from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    EmpleadoPersonal,
    PersonalApercibimiento,
    PersonalArt,
    PersonalCurso,
    PersonalEntregaEpp,
    PersonalEppItem,
    PersonalVacacion,
    User,
)
from app.user_roles import ROLE_SGI, ROLE_SOLO_LECTURA_TOTAL, normalize_stored_rol
from app.utils.datetime_operacion import now_operacion_naive_local

ROLES_SIN_LEGAJO: frozenset[str] = frozenset({ROLE_SOLO_LECTURA_TOTAL, ROLE_SGI})


def today_operacion() -> date:
    return now_operacion_naive_local().date()

ESTADOS_EMPLEADO = ("activo", "baja")
ESTADOS_VACACION = ("pendiente", "tomada", "cancelada")
ESTADOS_ENTREGA_EPP = ("pendiente", "confirmada")
TIPOS_APERCIBIMIENTO = ("verbal", "escrito")
CATEGORIAS_EPP = ("ropa", "epp", "otro")
CATEGORIAS_EPP_CON_WORKFLOW = frozenset({"ropa", "epp"})

ESTADO_EMPLEADO_LABELS = {"activo": "Activo", "baja": "Baja"}
ESTADO_VACACION_LABELS = {"pendiente": "Pendiente", "tomada": "Tomada", "cancelada": "Cancelada"}
ESTADO_ENTREGA_EPP_LABELS = {"pendiente": "Pendiente confirmación", "confirmada": "Confirmada"}
TIPO_APERCIBIMIENTO_LABELS = {"verbal": "Verbal", "escrito": "Escrito"}
CATEGORIA_EPP_LABELS = {"ropa": "Ropa", "epp": "EPP", "otro": "Otro"}

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


def ensure_empleado_for_user(user: User, *, commit: bool = True) -> EmpleadoPersonal | None:
    """Crea el legajo RRHH para un usuario si aún no existe."""
    if not user_requires_legajo(user):
        return None
    existing = (
        db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == user.id).first()
    )
    if existing is not None:
        return existing

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
    db.session.commit()
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
    if entrega is None:
        return False, "Entrega no encontrada."
    if entrega.estado != "pendiente":
        return False, "Esta entrega ya fue confirmada."
    emp = entrega.empleado
    if emp is None or emp.user_id is None or int(emp.user_id) != int(user_id):
        return False, "Solo el empleado titular puede confirmar esta entrega."
    if not item_epp_requiere_workflow(entrega.item):
        return False, "Esta entrega no requiere confirmación del empleado."
    if entrega.prenda_anterior_entrega_id is not None and not entrega.prenda_anterior_devuelta:
        return (
            False,
            "RRHH debe registrar la devolución de la prenda anterior antes de que puedas confirmar.",
        )

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
