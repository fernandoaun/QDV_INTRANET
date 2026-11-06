"""Checklists de inspección por equipo (registros del PO-01, p. ej. QDV-RG-PO-01_07 Check list de compresor de aire).

Cada equipo tiene su checklist: la lista de ítems del formulario en papel. Cada inspección guarda el estado de
cada ítem (Buen estado / Mal estado), queda firmada en el sistema por quien la hizo y después la firma el
Responsable de Planta, como las demás firmas por sistema (entregas de EPP, minutas). Todos los campos son
obligatorios.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import Equipo, MantChecklist, MantChecklistRegistro, User
from app.services.fichas_proceso_service import fecha_local
from app.services.plan_accion_service import fecha_dmy, parse_fecha

ESTADOS: tuple[str, ...] = ("Buen estado", "Mal estado")
SIN_OBSERVACIONES = "Sin observaciones."
REVISION = "00"


def items(c: MantChecklist | None) -> list[str]:
    if c is None:
        return []
    try:
        data = json.loads(c.items or "[]")
    except ValueError:
        return []
    return [str(x) for x in data if str(x).strip()]


def respuestas(r: MantChecklistRegistro) -> list[dict[str, str]]:
    try:
        data = json.loads(r.respuestas or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)]


def mal_estado(r: MantChecklistRegistro) -> list[str]:
    return [x["item"] for x in respuestas(r) if x.get("estado") == "Mal estado"]


def get_de_equipo(equipo_id: int) -> MantChecklist | None:
    return db.session.scalar(select(MantChecklist).where(MantChecklist.equipo_id == int(equipo_id)))


def listar_checklists() -> list[MantChecklist]:
    return list(db.session.scalars(
        select(MantChecklist).where(MantChecklist.activo.is_(True)).order_by(MantChecklist.codigo)
    ).unique())


def get_registro(registro_id: int) -> MantChecklistRegistro | None:
    r = db.session.get(MantChecklistRegistro, int(registro_id))
    return r if r is not None and r.activo else None


def registros(c: MantChecklist | None = None, limit: int = 200) -> list[MantChecklistRegistro]:
    q = select(MantChecklistRegistro).where(MantChecklistRegistro.activo.is_(True))
    if c is not None:
        q = q.where(MantChecklistRegistro.checklist_id == c.id)
    q = q.order_by(MantChecklistRegistro.fecha.desc(), MantChecklistRegistro.id.desc()).limit(limit)
    return list(db.session.scalars(q).unique())


def guardar_checklist(equipo: Equipo, data: Any) -> tuple[MantChecklist | None, list[str]]:
    """Alta o edición del checklist del equipo: código del registro, título y un ítem por renglón."""
    codigo = re.sub(r"\s+", " ", str(data.get("codigo") or "")).strip()[:64]
    titulo = re.sub(r"\s+", " ", str(data.get("titulo") or "")).strip()[:255]
    lista = [re.sub(r"\s+", " ", x).strip() for x in str(data.get("items") or "").splitlines()]
    lista = [x[:255] for x in lista if x]
    errores = []
    if not codigo:
        errores.append("Indicá el código del registro (por ejemplo QDV-RG-PO-01_07).")
    if not titulo:
        errores.append("Indicá el título del checklist.")
    if not lista:
        errores.append("Cargá al menos un ítem a inspeccionar (uno por renglón).")
    if errores:
        return None, errores
    c = get_de_equipo(equipo.id) or MantChecklist(equipo_id=equipo.id)
    c.codigo, c.titulo, c.items, c.activo = codigo, titulo, json.dumps(lista, ensure_ascii=False), True
    db.session.add(c)
    db.session.flush()
    return c, []


def registrar(c: MantChecklist, data: Any, user: User) -> tuple[MantChecklistRegistro | None, list[str]]:
    """Carga una inspección: todos los campos obligatorios; queda firmada por quien la carga."""
    from app.auth_utils import user_display_name

    errores: list[str] = []
    try:
        fecha = parse_fecha(data.get("fecha"))
        if fecha is None:
            errores.append("Fecha: es obligatoria.")
    except ValueError:
        fecha = None
        errores.append("Fecha: fecha inválida, usá dd/mm/aaaa.")
    area = re.sub(r"\s+", " ", str(data.get("area") or "")).strip()[:255]
    actividad = str(data.get("actividad") or "").strip()
    observaciones = str(data.get("observaciones") or "").strip()
    if not area:
        errores.append("Área: es obligatoria.")
    if not actividad:
        errores.append("Descripción de la actividad: es obligatoria.")
    resp = []
    for i, item in enumerate(items(c)):
        estado = str(data.get(f"item_{i}") or "").strip()
        if estado not in ESTADOS:
            errores.append(f"Marcá «Buen estado» o «Mal estado» en: {item}.")
        resp.append({"item": item, "estado": estado})
    malos = [x["item"] for x in resp if x["estado"] == "Mal estado"]
    if malos and not observaciones:
        errores.append("Hay ítems en mal estado: describí en observaciones qué se encontró.")
    if errores:
        return None, errores
    numero = (db.session.scalar(
        select(func.max(MantChecklistRegistro.numero)).where(MantChecklistRegistro.checklist_id == c.id)
    ) or 0) + 1
    r = MantChecklistRegistro(
        checklist_id=c.id, numero=numero, fecha=fecha, area=area, actividad=actividad,
        respuestas=json.dumps(resp, ensure_ascii=False), observaciones=observaciones or SIN_OBSERVACIONES,
        inspector_user_id=int(user.id), inspector_nombre=user_display_name(user),
        inspector_firma_at=datetime.now(timezone.utc),
    )
    db.session.add(r)
    db.session.flush()
    return r, []


def puede_firmar_planta(r: MantChecklistRegistro, user: User | None) -> bool:
    """La firma del Responsable de Planta la pone el administrador (Gerencia / Responsable de Planta)."""
    return user is not None and bool(user.is_admin) and r.planta_firma_at is None


def firmar_planta(r: MantChecklistRegistro, user: User) -> None:
    from app.auth_utils import user_display_name

    if r.planta_firma_at is not None:
        raise ValueError("El checklist ya tiene la firma del Responsable de Planta.")
    if not user.is_admin:
        raise ValueError("La firma del Responsable de Planta la pone el administrador.")
    r.planta_user_id = int(user.id)
    r.planta_nombre = user_display_name(user)
    r.planta_firma_at = datetime.now(timezone.utc)


def firma_texto(nombre: str, cuando: datetime | None) -> str:
    if cuando is None:
        return "Pendiente de firma"
    return f"Firmado en el sistema por {nombre} · {fecha_local(cuando)}"


def pendientes_firma_planta() -> list[MantChecklistRegistro]:
    return list(db.session.scalars(
        select(MantChecklistRegistro).where(
            MantChecklistRegistro.activo.is_(True), MantChecklistRegistro.planta_firma_at.is_(None)
        ).order_by(MantChecklistRegistro.fecha)
    ).unique())


def labels_context() -> dict[str, Any]:
    return {
        "ck_estados": ESTADOS, "ck_items": items, "ck_respuestas": respuestas, "ck_mal_estado": mal_estado,
        "ck_firma_texto": firma_texto, "fecha_dmy": fecha_dmy, "ck_revision": REVISION, "hoy": date.today(),
    }
