"""Constancia de entrega de ropa de trabajo y EPP (Res. SRT 299/11, Anexo I) — registro QDV-PO-02_01.

Arriba, una vez por trabajador: empresa, trabajador, (9) descripción del puesto y (10) EPP asignados.
Abajo, una fila por cada entrega registrada en Personal. La «firma» es la confirmación del trabajador
desde su usuario (aviso por mail), como hasta ahora.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import EmpleadoPersonal, PersonalEntregaEpp, PersonalEppAsignacion, PersonalEppItem, User

REGISTRO = {
    "codigo": "QDV-PO-02_01",
    "titulo": "CONSTANCIA DE ENTREGA EPP",
    "fecha_vigencia": date(2026, 9, 8),
    "revision": "00",
}
# Datos del empleador tal como figuran en el formulario.
EMPRESA = {
    "razon_social": "Quimica del Valle SRL.",
    "cuit": "30-70860737-8",
    "direccion": "Parque Industrial - Mzna 789 - Lote 7",
    "localidad": "Cinco Saltos",
    "cp": "8303",
    "provincia": "Río Negro",
}
FILAS_MINIMAS = 12


def _fecha_hora_local(dt: datetime | None) -> str:
    if dt is None:
        return ""
    from app.utils.datetime_operacion import operacion_zoneinfo

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(operacion_zoneinfo()).strftime("%d/%m/%Y %H:%M")


def firma_texto(e: PersonalEntregaEpp) -> str:
    """Columna (17): la confirmación del trabajador reemplaza a la firma en papel."""
    if e.estado != "confirmada":
        return "Pendiente de confirmación"
    cuando = _fecha_hora_local(e.confirmada_at)
    confirmo_el_trabajador = (
        e.confirmada_by_user_id is not None and e.empleado is not None and e.confirmada_by_user_id == e.empleado.user_id
    )
    if confirmo_el_trabajador:
        return f"Confirmado por el trabajador · {cuando}"
    quien = db.session.get(User, e.confirmada_by_user_id) if e.confirmada_by_user_id else None
    return f"Registrado por {quien.username if quien else 'RRHH'} · {cuando}"


def producto_texto(e: PersonalEntregaEpp) -> str:
    nombre = e.item.nombre if e.item else ""
    return f"{nombre} (talle {e.talle})" if e.talle else nombre


def entregas(emp: EmpleadoPersonal) -> list[PersonalEntregaEpp]:
    return list(
        db.session.scalars(
            select(PersonalEntregaEpp)
            .where(PersonalEntregaEpp.empleado_id == emp.id)
            .order_by(PersonalEntregaEpp.fecha.asc(), PersonalEntregaEpp.id.asc())
        )
    )


def asignados(emp: EmpleadoPersonal) -> list[PersonalEppItem]:
    rows = db.session.scalars(
        select(PersonalEppAsignacion).where(PersonalEppAsignacion.empleado_id == emp.id)
    ).unique()
    return sorted((a.item for a in rows if a.item is not None), key=lambda i: (i.orden, i.nombre))


def guardar_encabezado(emp: EmpleadoPersonal, form: Any) -> None:
    """(9) descripción del puesto y (10) EPP asignados. El llamador hace commit."""
    emp.epp_descripcion_puesto = (form.get("epp_descripcion_puesto") or "").strip()[:2000]
    elegidos = {int(x) for x in form.getlist("epp_asignados") if str(x).isdigit()}
    actuales = {
        a.item_id: a for a in db.session.scalars(select(PersonalEppAsignacion).where(PersonalEppAsignacion.empleado_id == emp.id))
    }
    for item_id, a in actuales.items():
        if item_id not in elegidos:
            db.session.delete(a)
    validos = set(db.session.scalars(select(PersonalEppItem.id).where(PersonalEppItem.id.in_(elegidos)))) if elegidos else set()
    for item_id in validos - set(actuales):
        db.session.add(PersonalEppAsignacion(empleado_id=emp.id, item_id=item_id))


def contexto(emp: EmpleadoPersonal | None) -> dict[str, Any]:
    filas = entregas(emp) if emp is not None else []
    return {
        "reg": REGISTRO,
        "empresa": EMPRESA,
        "emp": emp,
        "filas": filas,
        "asignados": asignados(emp) if emp is not None else [],
        "filas_vacias": max(FILAS_MINIMAS - len(filas), 0 if filas else FILAS_MINIMAS),
        "firma_texto": firma_texto,
        "producto_texto": producto_texto,
    }
