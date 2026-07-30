"""
Datos de demostración para desarrollo / prueba local.

Idempotente: se puede volver a ejecutar; solo completa lo que falte.
No usar en producción (contraseñas conocidas).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app.bootstrap import ensure_seed_data
from app.extensions import db
from app.models import (
    AguaRegistro,
    BolsonRegistro,
    ChoferEntrega,
    ClienteEntrega,
    EmpleadoPersonal,
    Entrega,
    Equipo,
    IngresoStock,
    LugarEntrega,
    MaintenanceFailure,
    MaintenanceOrder,
    MaintenancePlan,
    Operador,
    PlanificacionActividad,
    ProductoTerminado,
    ReactorRegistro,
    SalmueraAnalisis8hs,
    SalmueraRegistro,
    SectorVencimiento,
    User,
    Vencimiento,
)
from app.services import personal_service, stock_service
from app.user_roles import (
    ROLE_ADMINISTRADOR,
    ROLE_ADMINISTRACION,
    ROLE_LOGISTICA,
    ROLE_MANTENIMIENTO,
    ROLE_OPERACIONES,
    ROLE_SGI,
)
from app.utils.datetime_operacion import now_operacion_local_iso_seconds, now_operacion_naive_local

# Contraseña común de los usuarios demo (solo local).
DEMO_PASSWORD = "demo123"

# Prefijo para reconocer filas demo (entregas, equipos, etc.).
_DEMO_TAG = "[demo]"


def _now_iso() -> str:
    return now_operacion_local_iso_seconds()


def _today() -> date:
    return now_operacion_naive_local().date()


def _fecha_iso(d: date | None = None) -> str:
    return (d or _today()).isoformat()


def _get_or_create_user(
    username: str,
    *,
    rol: str,
    nombre_completo: str,
    is_admin: bool = False,
    password: str = DEMO_PASSWORD,
) -> tuple[User, bool]:
    name = username.strip().lower()
    existing = db.session.execute(
        select(User).where(sa_func.lower(User.username) == name)
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    u = User(
        username=name,
        nombre_completo=nombre_completo,
        password_hash=generate_password_hash(password),
        is_admin=is_admin,
        rol=rol,
        activo=True,
    )
    db.session.add(u)
    db.session.flush()
    return u, True


def _seed_catalog_stock(admin: User) -> list[str]:
    logs: list[str] = []
    ingresos = [
        ("materia_prima", "Sal industrial", "Salinas Demo", "2027-12-31", "DEMO-SAL-01", 2500.0, "kg"),
        ("materia_prima", "Soda cáustica", "Química Demo", "2027-06-30", "DEMO-SODA-01", 800.0, "kg"),
        ("laboratorio", "Ácido sulfúrico", "Lab Demo", "2027-03-31", "DEMO-LAB-01", 20.0, "L"),
        ("producto_terminado", "Hipoclorito", "Planta QDV", "2026-12-31", "DEMO-HIPO-01", 15000.0, "L"),
        ("producto_terminado", "Hipoclorito", "Planta QDV", "2026-11-30", "DEMO-HIPO-02", 8000.0, "L"),
    ]
    for cat, prod, marca, venc, lote, qty, unidad in ingresos:
        exists = db.session.scalar(
            select(sa_func.count()).select_from(IngresoStock).where(IngresoStock.lote == lote)
        )
        if int(exists or 0) > 0:
            logs.append(f"Ingreso ya existía: {lote}")
            continue
        stock_service.save_ingreso(
            cat,
            prod,
            marca,
            venc,
            lote,
            qty,
            "demo_ops",
            unidad=unidad,
            observaciones_ingreso=f"{_DEMO_TAG} stock local",
            proveedor="Proveedor Demo",
            cargado_por_user_id=int(admin.id),
            fecha=_fecha_iso(_today() - timedelta(days=3)),
            hora="09:00",
        )
        logs.append(f"Ingreso creado: {lote} ({prod} · {qty} {unidad})")
    return logs


def _seed_entregas_catalog() -> dict[str, Any]:
    now = _now_iso()
    out: dict[str, Any] = {}

    pt = db.session.execute(
        select(ProductoTerminado).where(ProductoTerminado.nombre == "Hipoclorito de Sodio")
    ).scalar_one_or_none()
    if pt is None:
        pt = ProductoTerminado(
            nombre="Hipoclorito de Sodio",
            stock_producto="Hipoclorito",
            activo=True,
            created_at_iso=now,
            updated_at_iso=now,
        )
        db.session.add(pt)
        db.session.flush()

    def _cliente(nombre: str) -> ClienteEntrega:
        row = db.session.execute(
            select(ClienteEntrega).where(ClienteEntrega.nombre == nombre)
        ).scalar_one_or_none()
        if row is not None:
            return row
        row = ClienteEntrega(
            nombre=nombre,
            activo=True,
            observaciones=f"{_DEMO_TAG} cliente local",
            created_at_iso=now,
            updated_at_iso=now,
        )
        db.session.add(row)
        db.session.flush()
        return row

    c1 = _cliente("Cliente Demo Norte")
    c2 = _cliente("Cliente Demo Sur")

    def _lugar(nombre: str, cliente: ClienteEntrega) -> LugarEntrega:
        row = db.session.execute(
            select(LugarEntrega).where(
                LugarEntrega.nombre == nombre,
                LugarEntrega.cliente_id == int(cliente.id),
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
        row = LugarEntrega(
            nombre=nombre,
            cliente_id=int(cliente.id),
            activo=True,
            created_at_iso=now,
            updated_at_iso=now,
        )
        db.session.add(row)
        db.session.flush()
        return row

    l1 = _lugar("Depósito Norte", c1)
    l2 = _lugar("Planta Sur", c2)

    ch = db.session.execute(
        select(ChoferEntrega).where(ChoferEntrega.nombre == "Chofer Demo")
    ).scalar_one_or_none()
    if ch is None:
        ch = ChoferEntrega(
            nombre="Chofer Demo",
            activo=True,
            observaciones=f"{_DEMO_TAG}",
            created_at_iso=now,
            updated_at_iso=now,
        )
        db.session.add(ch)
        db.session.flush()

    db.session.commit()
    out.update(pt=pt, c1=c1, c2=c2, l1=l1, l2=l2, ch=ch)
    return out


def _seed_entregas(catalog: dict[str, Any], admin: User) -> list[str]:
    logs: list[str] = []
    now = _now_iso()
    pt = catalog["pt"]
    c1, c2 = catalog["c1"], catalog["c2"]
    l1, l2 = catalog["l1"], catalog["l2"]
    ch = catalog["ch"]

    specs = [
        {
            "cliente": c1.nombre,
            "lugar": l1.nombre,
            "cliente_id": int(c1.id),
            "lugar_id": int(l1.id),
            "cantidad": 5000.0,
            "fecha": _fecha_iso(_today() + timedelta(days=2)),
            "estado": "programada",
            "obs": f"{_DEMO_TAG} entrega programada",
        },
        {
            "cliente": c2.nombre,
            "lugar": l2.nombre,
            "cliente_id": int(c2.id),
            "lugar_id": int(l2.id),
            "cantidad": 3000.0,
            "fecha": _fecha_iso(_today() + timedelta(days=5)),
            "estado": "programada",
            "obs": f"{_DEMO_TAG} entrega programada 2",
        },
    ]
    for s in specs:
        exists = db.session.execute(
            select(Entrega).where(
                Entrega.observaciones == s["obs"],
                Entrega.cliente_id == s["cliente_id"],
            )
        ).scalar_one_or_none()
        if exists is not None:
            logs.append(f"Entrega ya existía: {s['obs']}")
            continue
        db.session.add(
            Entrega(
                cliente=s["cliente"],
                lugar_entrega=s["lugar"],
                producto=pt.nombre,
                cliente_id=s["cliente_id"],
                lugar_entrega_id=s["lugar_id"],
                producto_terminado_id=int(pt.id),
                chofer_entrega_id=int(ch.id),
                cantidad=s["cantidad"],
                cantidad_programada=s["cantidad"],
                unidad="L",
                fecha_prevista=s["fecha"],
                observaciones=s["obs"],
                chofer_previsto=ch.nombre,
                estado=s["estado"],
                created_at_iso=now,
                updated_at_iso=now,
                created_by_user_id=int(admin.id),
            )
        )
        logs.append(f"Entrega creada: {s['cliente']} · {s['cantidad']} L")
    db.session.commit()
    return logs


def _seed_equipos_y_mant() -> list[str]:
    logs: list[str] = []
    now = _now_iso()

    def _equipo(codigo: str, nombre: str, tipo: str, area: str) -> Equipo:
        row = db.session.execute(
            select(Equipo).where(Equipo.codigo_interno == codigo)
        ).scalar_one_or_none()
        if row is not None:
            return row
        row = Equipo(
            codigo_interno=codigo,
            nombre_equipo=nombre,
            descripcion=f"{_DEMO_TAG} {nombre}",
            tipo_equipo=tipo,
            area_sector=area,
            estado="operativo",
            activo=True,
            fecha_alta=_fecha_iso(_today() - timedelta(days=120)),
            created_at_iso=now,
        )
        db.session.add(row)
        db.session.flush()
        logs.append(f"Equipo creado: {codigo}")
        return row

    el1 = _equipo("DEMO-EL-01", "Electrolizador 1", "Electrolizador", "Producción")
    bomba = _equipo("DEMO-BM-01", "Bomba de salmuera", "Bomba", "Producción")
    _equipo("DEMO-RX-01", "Reactor 1", "Reactor", "Producción")

    plan = db.session.execute(
        select(MaintenancePlan).where(MaintenancePlan.nombre == f"{_DEMO_TAG} Preventivo electrolizador")
    ).scalar_one_or_none()
    if plan is None:
        plan = MaintenancePlan(
            equipo_id=int(el1.id),
            tipo_mantenimiento="preventivo",
            nombre=f"{_DEMO_TAG} Preventivo electrolizador",
            frecuencia_dias=30,
            proxima_fecha=_fecha_iso(_today() + timedelta(days=10)),
            responsable="demo_mant",
            duracion_estimada_horas=4.0,
            tareas="Inspección de celdas, limpieza y control de conexiones.",
            activo=True,
            created_at_iso=now,
            updated_at_iso=now,
        )
        db.session.add(plan)
        db.session.flush()
        logs.append("Plan de mantenimiento creado")

    order = db.session.execute(
        select(MaintenanceOrder).where(
            MaintenanceOrder.observaciones == f"{_DEMO_TAG} OT programada"
        )
    ).scalar_one_or_none()
    if order is None:
        db.session.add(
            MaintenanceOrder(
                plan_id=int(plan.id),
                equipo_id=int(el1.id),
                tipo_mantenimiento="preventivo",
                fecha_programada=_fecha_iso(_today() + timedelta(days=10)),
                prioridad="media",
                criticidad="media",
                responsable="demo_mant",
                estado="programado",
                tareas=plan.tareas,
                tiempo_estimado_horas=4.0,
                observaciones=f"{_DEMO_TAG} OT programada",
                created_at_iso=now,
                updated_at_iso=now,
            )
        )
        logs.append("Orden de mantenimiento creada")

    fail = db.session.execute(
        select(MaintenanceFailure).where(
            MaintenanceFailure.descripcion_falla == f"{_DEMO_TAG} Ruido anormal en bomba"
        )
    ).scalar_one_or_none()
    if fail is None:
        db.session.add(
            MaintenanceFailure(
                detected_at_iso=now,
                equipo_id=int(bomba.id),
                reported_by_display="demo_ops",
                descripcion_falla=f"{_DEMO_TAG} Ruido anormal en bomba",
                sintoma_observado="Vibración y ruido metálico al arrancar.",
                causa_probable="Rodamiento desgastado",
                criticidad="media",
                estado="reportado",
                created_at_iso=now,
                updated_at_iso=now,
            )
        )
        logs.append("Falla de mantenimiento reportada")

    db.session.commit()
    return logs


def _seed_produccion() -> list[str]:
    logs: list[str] = []
    now = _now_iso()
    op = db.session.execute(select(Operador).order_by(Operador.id)).scalars().first()
    op_nombre = op.nombre if op else "Operador 1"
    base = _today() - timedelta(days=2)

    # Marca: lote demo único
    lote_marker = "DEMO-LOTE-001"
    if db.session.scalar(
        select(sa_func.count()).select_from(SalmueraRegistro).where(SalmueraRegistro.lote == lote_marker)
    ):
        logs.append("Registros de producción demo ya existían")
        return logs

    volts = [3.05, 3.02, 3.08, 3.01, 3.04, 3.06]
    for day_offset, hora, turno in ((0, "08:00", "Mañana"), (0, "16:00", "Tarde"), (1, "08:00", "Mañana")):
        d = base + timedelta(days=day_offset)
        db.session.add(
            SalmueraRegistro(
                fecha_iso=_fecha_iso(d),
                hora_hm=hora,
                electrolizador=1,
                cantidad_celdas=6,
                turno=turno,
                voltajes_json=json.dumps(volts),
                voltaje_total=round(sum(volts), 2),
                voltaje_total_trafo=18.5,
                amperaje=1850.0,
                caudal_agua_l_h=420.0,
                caudal_salmuera_l_h=380.0,
                hipo_conc=12.5,
                hipo_exceso_soda=0.8,
                sal_temp=28.0,
                sal_conc=310.0,
                sal_ph=7.2,
                soda_conc=18.0,
                declor_ph=6.8,
                orp=650.0,
                operador=op_nombre,
                lote=lote_marker if day_offset == 0 and hora == "08:00" else f"DEMO-LOTE-{day_offset}-{hora[:2]}",
                observaciones=f"{_DEMO_TAG} registro salmuera",
                created_at_iso=now,
            )
        )

    db.session.add(
        SalmueraAnalisis8hs(
            fecha=_fecha_iso(base),
            hora="08:00",
            fecha_hora_iso=f"{_fecha_iso(base)}T08:00:00",
            turno="Mañana",
            operador=op_nombre,
            dureza_salmuera=1.2,
            cloro_libre_salmuera=0.05,
            observaciones=f"{_DEMO_TAG} análisis 8hs",
            created_at_iso=now,
        )
    )
    db.session.add(
        ReactorRegistro(
            fecha_iso=_fecha_iso(base),
            hora_hm="09:30",
            operador=op_nombre,
            lote=lote_marker,
            ph=11.2,
            temperatura=32.0,
            densidad=1.18,
            concentracion_tabla=12.4,
            exceso_naoh=0.5,
            exceso_na2co3=0.2,
            orp=580.0,
            observaciones=f"{_DEMO_TAG} reactor",
            created_at_iso=now,
        )
    )
    db.session.add(
        AguaRegistro(
            fecha_iso=_fecha_iso(base),
            hora_hm="07:45",
            turno="Mañana",
            operador=op_nombre,
            lote=lote_marker,
            numero_columna=1,
            temperatura=22.0,
            dureza=0.5,
            observaciones=f"{_DEMO_TAG} agua",
            created_at_iso=now,
        )
    )
    db.session.add(
        BolsonRegistro(
            fecha_iso=_fecha_iso(base),
            hora_hm="10:00",
            created_at_iso=now,
        )
    )
    db.session.commit()
    logs.append("Registros de producción demo creados (salmuera, reactor, agua, bolsón)")
    return logs


def _seed_personal(users_by_name: dict[str, User]) -> list[str]:
    logs: list[str] = []
    personal_service.ensure_default_epp_catalog()

    op = db.session.execute(select(Operador).order_by(Operador.id)).scalars().first()
    specs = [
        ("demo_ops", "DEMO-001", "Gómez", "Juan", "Operador de planta", "Producción"),
        ("demo_log", "DEMO-002", "López", "María", "Logística", "Logística"),
        ("demo_mant", "DEMO-003", "Pérez", "Carlos", "Técnico mantenimiento", "Mantenimiento"),
    ]
    for username, legajo, apellido, nombre, puesto, area in specs:
        user = users_by_name.get(username)
        if user is None:
            continue
        existing = db.session.execute(
            select(EmpleadoPersonal).where(EmpleadoPersonal.legajo == legajo)
        ).scalar_one_or_none()
        if existing is not None:
            logs.append(f"Legajo ya existía: {legajo}")
            continue
        if user.empleado_personal is not None:
            logs.append(f"Usuario {username} ya tiene legajo")
            continue
        emp = EmpleadoPersonal(
            user_id=int(user.id),
            legajo=legajo,
            dni=f"30{legajo[-3:]}00001",
            cuil=f"20-30{legajo[-3:]}00001-1",
            apellido=apellido,
            nombre=nombre,
            fecha_nacimiento=date(1990, 5, 15),
            domicilio="Calle Demo 123",
            telefono="011-5555-0000",
            email=f"{username}@demo.local",
            puesto=puesto,
            area=area,
            fecha_ingreso=_today() - timedelta(days=400),
            estado="activo",
            talle_pantalon="42",
            talle_camisa="L",
            talle_calzado="42",
            observaciones=f"{_DEMO_TAG} legajo local",
            operador_id=int(op.id) if op and username == "demo_ops" else None,
            created_by_id=int(users_by_name["admin"].id) if "admin" in users_by_name else None,
        )
        db.session.add(emp)
        logs.append(f"Legajo creado: {legajo} ({apellido}, {nombre})")
    db.session.commit()
    return logs


def _seed_planificacion(admin: User, ops: User | None) -> list[str]:
    logs: list[str] = []
    codigo = "DEMO-PLAN-01"
    exists = db.session.execute(
        select(PlanificacionActividad).where(PlanificacionActividad.codigo == codigo)
    ).scalar_one_or_none()
    if exists is not None:
        logs.append("Planificación demo ya existía")
        return logs
    inicio = _today()
    fin = inicio + timedelta(days=4)
    db.session.add(
        PlanificacionActividad(
            codigo=codigo,
            titulo=f"{_DEMO_TAG} Revisión de stock PT",
            descripcion="Actividad de ejemplo para probar el módulo de planificación.",
            fecha_inicio=inicio,
            fecha_fin=fin,
            duracion_dias=PlanificacionActividad.compute_duracion_dias(inicio, fin),
            responsable_user_id=int(ops.id) if ops else int(admin.id),
            categoria="produccion",
            prioridad="media",
            estado="pendiente",
            observaciones=_DEMO_TAG,
            created_by_user_id=int(admin.id),
        )
    )
    db.session.commit()
    logs.append("Actividad de planificación creada")
    return logs


def _seed_vencimientos(admin: User) -> list[str]:
    logs: list[str] = []
    sector = db.session.execute(
        select(SectorVencimiento).where(SectorVencimiento.nombre == "Demo Planta")
    ).scalar_one_or_none()
    if sector is None:
        sector = SectorVencimiento(
            nombre="Demo Planta",
            descripcion=f"{_DEMO_TAG} sector de vencimientos",
            activo=True,
            created_by_id=int(admin.id),
        )
        db.session.add(sector)
        db.session.flush()
        logs.append("Sector de vencimientos creado")

    marker = f"{_DEMO_TAG} Matrícula caldera"
    exists = db.session.execute(
        select(Vencimiento).where(Vencimiento.nombre == marker)
    ).scalar_one_or_none()
    if exists is None:
        db.session.add(
            Vencimiento(
                sector_id=int(sector.id),
                nombre=marker,
                descripcion="Documento de ejemplo próximo a vencer.",
                fecha_vencimiento=_today() + timedelta(days=20),
                responsable="demo_mant",
                email_aviso="avisos@demo.local",
                estado="vigente",
                observaciones=_DEMO_TAG,
                activo=True,
                created_by_id=int(admin.id),
                updated_by_id=int(admin.id),
            )
        )
        logs.append("Vencimiento demo creado")
    else:
        logs.append("Vencimiento demo ya existía")
    db.session.commit()
    return logs


def seed_demo_data(*, password: str = DEMO_PASSWORD) -> dict[str, Any]:
    """
    Carga datos de prueba locales. Idempotente.

    Returns:
        dict con `ok`, `password`, `users`, `logs`.
    """
    pwd = (password or DEMO_PASSWORD).strip() or DEMO_PASSWORD
    ensure_seed_data()

    logs: list[str] = []
    created_users: list[str] = []
    specs = [
        ("admin", ROLE_ADMINISTRADOR, "Administrador Demo", True),
        ("demo_ops", ROLE_OPERACIONES, "Operador Demo", False),
        ("demo_log", ROLE_LOGISTICA, "Logística Demo", False),
        ("demo_adm", ROLE_ADMINISTRACION, "Administración Demo", False),
        ("demo_mant", ROLE_MANTENIMIENTO, "Mantenimiento Demo", False),
        ("demo_sgi", ROLE_SGI, "SGC Demo", False),
    ]
    users_by_name: dict[str, User] = {}
    for username, rol, nombre, is_admin in specs:
        u, created = _get_or_create_user(
            username, rol=rol, nombre_completo=nombre, is_admin=is_admin, password=pwd
        )
        users_by_name[username] = u
        if created:
            created_users.append(username)
            logs.append(f"Usuario creado: {username} ({rol})")
        else:
            logs.append(f"Usuario ya existía: {username}")
    db.session.commit()

    admin = users_by_name["admin"]
    logs.extend(_seed_catalog_stock(admin))
    catalog = _seed_entregas_catalog()
    logs.append("Catálogos de entregas listos (clientes, lugares, chofer, PT)")
    logs.extend(_seed_entregas(catalog, admin))
    logs.extend(_seed_equipos_y_mant())
    logs.extend(_seed_produccion())
    logs.extend(_seed_personal(users_by_name))
    logs.extend(_seed_planificacion(admin, users_by_name.get("demo_ops")))
    logs.extend(_seed_vencimientos(admin))

    return {
        "ok": True,
        "password": pwd,
        "users": [
            {"username": u, "rol": r, "created": u in created_users}
            for u, r, _, _ in specs
        ],
        "created_users": created_users,
        "logs": logs,
    }
