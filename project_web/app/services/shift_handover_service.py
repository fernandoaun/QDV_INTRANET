"""
Cambio de turno operativo: consultas, reglas de negocio y armado de partes.

Consumos en la ventana del turno: se listan todos los consumos de stock con
created_at_iso entre inicio de sesión y cierre (alcance de planta en ese período;
columna operador indica quién registró).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import select

from app.auth_utils import user_display_name
from app.extensions import db
from app.models import (
    AguaRegistro,
    ReactorRegistro,
    SalmueraRegistro,
    ShiftHandover,
    ShiftHandoverWarningAction,
    ShiftSession,
    User,
)
from app.repositories.shift_repository import shift_repo
from app.repositories.stock_repository import stock_repo
from app.repositories.user_repository import user_repo
from app.services.operational_warnings import (
    warnings_for_agua_registro,
    warnings_for_reactor_registro,
    warnings_for_salmuera_registro,
)
from app.user_roles import ROLE_LABORATORISTA, ROLE_OPERACIONES, normalize_stored_rol

SESSION_KEY_SHIFT_DECLINED = "shift_operational_declined"

# Etiquetas de origen para parte de entrega (coherente con módulos de planta)
ORIGIN_HIPOCLORITO = "Control hipoclorito"
ORIGIN_CIRCUITO_SALMUERA_FUSION = "Circuito de salmuera (fusión)"
ORIGIN_CIRCUITO_AGUA = "Circuito de agua"

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"
HANDOVER_PENDING = "pending_reception"
HANDOVER_RECEIVED = "received"
RECEPTION_ACCEPTED = "accepted"
RECEPTION_WITH_OBS = "accepted_with_observations"


def now_local_iso() -> str:
    from app.utils.datetime_operacion import now_operacion_local_iso_seconds

    return now_operacion_local_iso_seconds()


def user_participates_operational_shift(user: User | None) -> bool:
    """Solo el perfil operaciones toma y opera turno; laboratorista no inicia sesión ni entra aquí."""
    if user is None or user.is_admin:
        return False
    r = normalize_stored_rol(user.rol)
    return r == ROLE_OPERACIONES


def user_can_view_shift_handover_notifications(user: User | None) -> bool:
    """Quién ve la campana de observaciones (misma base que historial de cambio de turno)."""
    if user is None:
        return False
    if user.is_admin:
        return True
    if user_participates_operational_shift(user):
        return True
    from app.auth_utils import user_can_access_production_hub

    return user_can_access_production_hub(user)


def operador_matches_user(row_operador: str | None, user: User) -> bool:
    a = (row_operador or "").strip().lower()
    b = (user.username or "").strip().lower()
    return bool(a and b and a == b)


def get_open_shift_session() -> ShiftSession | None:
    return shift_repo.get_open_shift_session()


def get_pending_handover() -> ShiftHandover | None:
    return shift_repo.get_pending_handover()


def get_shift_session_for_user(user: User) -> ShiftSession | None:
    return shift_repo.get_shift_session_for_user(int(user.id))


def list_active_laboratorista_users() -> list[User]:
    return user_repo.list_active_laboratorista_users()


def validate_laboratorist_user_id(uid: int) -> str | None:
    """None si el usuario puede figurar como laboratorista acompañante; si no, mensaje de error."""
    u = user_repo.get_by_id(uid)
    if u is None:
        return "El usuario indicado no existe."
    if not u.activo:
        return "El laboratorista indicado no está activo."
    if u.is_admin:
        return "Perfil no válido como laboratorista acompañante."
    if normalize_stored_rol(u.rol) != ROLE_LABORATORISTA:
        return "El usuario elegido no tiene perfil laboratorista."
    return None


def resolve_laboratorist_from_form(with_laboratorist: str | None, raw_user_id: str | None) -> tuple[int | None, str | None]:
    """
    Devuelve (laboratorist_user_id o None, mensaje_error).
    with_laboratorist: 'si' | 'no' (normalizado minúsculas).
    """
    mode = (with_laboratorist or "").strip().lower()
    if mode == "no":
        return None, None
    if mode != "si":
        return None, "Indicá si trabajás con laboratorista (sí o no)."
    s = (raw_user_id or "").strip()
    if not s:
        return None, "Elegí el laboratorista o indicá que no trabajás con uno."
    try:
        uid = int(s)
    except ValueError:
        return None, "Selección de laboratorista inválida."
    err = validate_laboratorist_user_id(uid)
    if err:
        return None, err
    return uid, None


def format_shift_operator_display(sess: ShiftSession | None) -> str:
    """Operador responsable del turno, con laboratorista acompañante si corresponde."""
    if sess is None:
        return ""
    op = sess.user
    base = user_display_name(op) or ((op.username or "").strip() if op else "")
    if not base:
        return ""
    lid = getattr(sess, "laboratorist_user_id", None)
    if lid is None:
        return base
    lab = sess.laboratorist_user
    if lab is None:
        lab = user_repo.get_by_id(int(lid))
    lab_name = user_display_name(lab) or ((lab.username or "").strip() if lab else "")
    if lab_name:
        return f"{base} (Laboratorista: {lab_name})"
    return base


def operador_turno_display_line(user: User | None, open_s: ShiftSession | None = None) -> str:
    """Línea de operador para formularios del usuario actual y su turno abierto (si es titular)."""
    if user is None:
        return ""
    os = open_s if open_s is not None else get_open_shift_session()
    if os is not None and int(os.user_id) == int(user.id):
        return format_shift_operator_display(os)
    return user_display_name(user) or (user.username or "").strip()


def user_has_open_shift(user: User) -> bool:
    return get_shift_session_for_user(user) is not None


@dataclass
class OperationalMutationDenial:
    allowed: bool
    message: str | None = None


def assert_may_mutate_operational(user: User, session_declined: bool) -> OperationalMutationDenial:
    """Perfil operaciones: requiere turno activo propio y no entrega pendiente."""
    pending = get_pending_handover()
    if pending is not None:
        return OperationalMutationDenial(
            False,
            "Hay una entrega de turno pendiente de recepción. Recepcioná el parte en Operación → Cambio de turno antes de cargar datos operativos.",
        )
    if session_declined:
        return OperationalMutationDenial(
            False,
            "Indicaste que no tomabas turno. Tomá turno desde Producción u Operación para habilitar cargas.",
        )
    open_s = get_open_shift_session()
    if open_s is None:
        return OperationalMutationDenial(
            False,
            "No hay turno operativo activo. Tomá turno desde Producción u Operación.",
        )
    if int(open_s.user_id) != int(user.id):
        out = user_repo.get_by_id(int(open_s.user_id))
        label = format_shift_operator_display(open_s) if open_s else ((out.username if out else "?") if out else "otro operador")
        return OperationalMutationDenial(
            False,
            f"El turno está a cargo de {label}. Coordiná la entrega de turno antes de registrar operaciones.",
        )
    return OperationalMutationDenial(True, None)


def consumos_en_intervalo(started_at_iso: str, ended_at_iso: str) -> list[dict[str, Any]]:
    """
    Consumos con created_at_iso en [started, ended] (inclusive por comparación lexicográfica ISO).
    """
    rows = stock_repo.list_consumos_stock_in_interval(started_at_iso, ended_at_iso)
    eq_ids = {int(c.equipo_id) for c in rows if c.equipo_id is not None}
    eq_map = stock_repo.equipo_nombres_by_ids(eq_ids)
    out: list[dict[str, Any]] = []
    for c in rows:
        eq_label = "—"
        if c.equipo_id is not None and int(c.equipo_id) in eq_map:
            eq_label = eq_map[int(c.equipo_id)] or "—"
        out.append(
            {
                "id": c.id,
                "created_at_iso": c.created_at_iso,
                "fecha": c.fecha,
                "hora": c.hora,
                "producto": c.producto,
                "marca": c.marca,
                "categoria": c.categoria,
                "cantidad": c.cantidad,
                "unidad": "",
                "equipo": eq_label,
                "operador": c.operador,
                "observaciones": (c.observaciones or "").strip(),
            }
        )
    return out


@dataclass
class WarningItem:
    source_type: str
    source_record_id: int
    warning_index: int
    warning_code: str
    warning_message: str
    record_label: str
    record_created_at_iso: str
    record_fecha_iso: str
    record_hora_hm: str
    origin_display: str


def _in_time_window(created_iso: str, start_iso: str, end_iso: str) -> bool:
    c = (created_iso or "").strip()
    if not c:
        return False
    return c >= start_iso and c <= end_iso


def collect_warning_items_for_user(user: User, started_at_iso: str, ended_at_iso: str) -> list[WarningItem]:
    """Registros del usuario con al menos un aviso, en la ventana temporal."""
    items: list[WarningItem] = []

    sal_rows = db.session.scalars(
        select(SalmueraRegistro)
        .where(
            SalmueraRegistro.created_at_iso >= started_at_iso,
            SalmueraRegistro.created_at_iso <= ended_at_iso,
        )
        .order_by(SalmueraRegistro.id.desc())
        .limit(2000)
    ).all()
    for r in sal_rows:
        if not operador_matches_user(r.operador, user):
            continue
        if not _in_time_window(r.created_at_iso, started_at_iso, ended_at_iso):
            continue
        warns = warnings_for_salmuera_registro(r)
        if not warns:
            continue
        for i, msg in enumerate(warns):
            cra = (r.created_at_iso or "").strip()
            items.append(
                WarningItem(
                    source_type="salmuera",
                    source_record_id=int(r.id),
                    warning_index=i,
                    warning_code=f"salmuera:{r.id}:{i}",
                    warning_message=msg,
                    record_label=f"{ORIGIN_HIPOCLORITO} · {r.fecha_iso} {r.hora_hm} · lote {r.lote or '—'}",
                    record_created_at_iso=cra,
                    record_fecha_iso=(r.fecha_iso or "").strip(),
                    record_hora_hm=(r.hora_hm or "").strip(),
                    origin_display=ORIGIN_HIPOCLORITO,
                )
            )

    rx_rows = db.session.scalars(
        select(ReactorRegistro)
        .where(
            ReactorRegistro.created_at_iso >= started_at_iso,
            ReactorRegistro.created_at_iso <= ended_at_iso,
        )
        .order_by(ReactorRegistro.id.desc())
        .limit(2000)
    ).all()
    for r in rx_rows:
        if not operador_matches_user(r.operador, user):
            continue
        if not _in_time_window(r.created_at_iso, started_at_iso, ended_at_iso):
            continue
        warns = warnings_for_reactor_registro(r)
        if not warns:
            continue
        for i, msg in enumerate(warns):
            cra = (r.created_at_iso or "").strip()
            items.append(
                WarningItem(
                    source_type="reactor",
                    source_record_id=int(r.id),
                    warning_index=i,
                    warning_code=f"reactor:{r.id}:{i}",
                    warning_message=msg,
                    record_label=f"{ORIGIN_CIRCUITO_SALMUERA_FUSION} · {r.fecha_iso} {r.hora_hm} · lote {r.lote or '—'}",
                    record_created_at_iso=cra,
                    record_fecha_iso=(r.fecha_iso or "").strip(),
                    record_hora_hm=(r.hora_hm or "").strip(),
                    origin_display=ORIGIN_CIRCUITO_SALMUERA_FUSION,
                )
            )

    ag_rows = db.session.scalars(
        select(AguaRegistro)
        .where(
            AguaRegistro.created_at_iso >= started_at_iso,
            AguaRegistro.created_at_iso <= ended_at_iso,
        )
        .order_by(AguaRegistro.id.desc())
        .limit(2000)
    ).all()
    for r in ag_rows:
        if not operador_matches_user(r.operador, user):
            continue
        if not _in_time_window(r.created_at_iso, started_at_iso, ended_at_iso):
            continue
        warns = warnings_for_agua_registro(r)
        if not warns:
            continue
        for i, msg in enumerate(warns):
            cra = (r.created_at_iso or "").strip()
            items.append(
                WarningItem(
                    source_type="agua",
                    source_record_id=int(r.id),
                    warning_index=i,
                    warning_code=f"agua:{r.id}:{i}",
                    warning_message=msg,
                    record_label=f"{ORIGIN_CIRCUITO_AGUA} · {r.fecha_iso} {r.hora_hm} · col {r.numero_columna}",
                    record_created_at_iso=cra,
                    record_fecha_iso=(r.fecha_iso or "").strip(),
                    record_hora_hm=(r.hora_hm or "").strip(),
                    origin_display=ORIGIN_CIRCUITO_AGUA,
                )
            )

    items.sort(
        key=lambda x: (
            x.record_created_at_iso or "",
            x.source_type,
            x.source_record_id,
            x.warning_index,
        )
    )
    return items


def handover_to_detail_dict(h: ShiftHandover) -> dict[str, Any]:
    outgoing = user_repo.get_by_id(int(h.outgoing_user_id))
    incoming = user_repo.get_by_id(int(h.incoming_user_id)) if h.incoming_user_id else None
    sess = h.shift_session
    if sess is None:
        sess = shift_repo.get_shift_session_by_id(int(h.shift_session_id))
    outgoing_operator_display = format_shift_operator_display(sess) if sess else (
        user_display_name(outgoing) or (outgoing.username if outgoing else "")
    )
    consumos = consumos_en_intervalo(h.shift_started_at_iso, h.handed_over_at_iso)
    actions = list(h.warning_actions) if h.warning_actions else []
    actions_sorted = sorted(
        actions,
        key=lambda a: ((getattr(a, "record_created_at_iso", None) or "").strip(), a.id),
    )
    return {
        "id": h.id,
        "outgoing_username": (outgoing.username if outgoing else ""),
        "outgoing_name": (outgoing.nombre_completo or outgoing.username if outgoing else ""),
        "outgoing_operator_display": outgoing_operator_display,
        "incoming_username": (incoming.username if incoming else ""),
        "incoming_name": (incoming.nombre_completo or incoming.username if incoming else ""),
        "shift_started_at_iso": h.shift_started_at_iso,
        "handed_over_at_iso": h.handed_over_at_iso,
        "received_at_iso": h.received_at_iso,
        "hypochlorite_stock_liters": h.hypochlorite_stock_liters,
        "closing_notes": h.closing_notes or "",
        "reception_status": h.reception_status,
        "reception_notes": h.reception_notes or "",
        "status": h.status,
        "consumos": consumos,
        "warning_actions": [
            {
                "source_type": a.source_type,
                "source_record_id": a.source_record_id,
                "warning_message": a.warning_message,
                "action_taken": a.action_taken,
                "record_created_at_iso": (getattr(a, "record_created_at_iso", None) or "").strip(),
                "origin_display": (getattr(a, "origin_display", None) or "").strip(),
            }
            for a in actions_sorted
        ],
    }


def list_handovers_for_history(limit: int = 200) -> list[ShiftHandover]:
    return shift_repo.list_handovers_for_history(limit)


def persist_new_open_shift_session(user: User, laboratorist_user_id: int | None) -> None:
    if get_pending_handover() is not None:
        raise ValueError("Antes debés recepcionar la entrega de turno pendiente.")
    if get_open_shift_session() is not None:
        raise ValueError("Ya hay un turno activo.")
    if laboratorist_user_id is not None:
        vmsg = validate_laboratorist_user_id(int(laboratorist_user_id))
        if vmsg:
            raise ValueError(vmsg)
    now_iso = now_local_iso()
    eff = normalize_stored_rol(user.rol)
    row = ShiftSession(
        user_id=user.id,
        laboratorist_user_id=laboratorist_user_id,
        effective_role=eff,
        started_at_iso=now_iso,
        ended_at_iso=None,
        status=STATUS_OPEN,
        created_at_iso=now_iso,
        updated_at_iso=now_iso,
    )
    db.session.add(row)
    db.session.commit()


def persist_handover_submission(
    form: Any,
    user: User,
    sess: ShiftSession,
    warn_items: list[WarningItem],
    now_iso: str,
) -> None:
    raw_stock = (form.get("hypochlorite_stock_liters") or "").strip().replace(",", ".")
    if raw_stock == "":
        raise ValueError("El stock final de hipoclorito (litros) es obligatorio.")
    stock_l = float(raw_stock)
    if stock_l < 0 or not math.isfinite(stock_l):
        raise ValueError("Stock de hipoclorito inválido.")
    closing_notes = (form.get("closing_notes") or "").strip()
    for w in warn_items:
        key = f"action_{w.source_type}_{w.source_record_id}_{w.warning_index}"
        act = (form.get(key) or "").strip()
        if not act:
            raise ValueError(f"Completá la acción tomada para el aviso: {w.warning_message}")
    ho = ShiftHandover(
        shift_session_id=sess.id,
        outgoing_user_id=user.id,
        incoming_user_id=None,
        shift_started_at_iso=sess.started_at_iso,
        handed_over_at_iso=now_iso,
        received_at_iso=None,
        hypochlorite_stock_liters=stock_l,
        closing_notes=closing_notes or None,
        reception_status=None,
        reception_notes=None,
        status=HANDOVER_PENDING,
        created_at_iso=now_iso,
        updated_at_iso=now_iso,
    )
    db.session.add(ho)
    db.session.flush()
    for w in warn_items:
        key = f"action_{w.source_type}_{w.source_record_id}_{w.warning_index}"
        act = (form.get(key) or "").strip()
        db.session.add(
            ShiftHandoverWarningAction(
                handover_id=ho.id,
                source_type=w.source_type,
                source_record_id=w.source_record_id,
                warning_code=w.warning_code,
                warning_message=w.warning_message,
                action_taken=act,
                created_at_iso=now_iso,
                record_created_at_iso=w.record_created_at_iso or None,
                origin_display=w.origin_display or None,
            )
        )
    sess.status = STATUS_CLOSED
    sess.ended_at_iso = now_iso
    sess.updated_at_iso = now_iso
    db.session.commit()


def persist_handover_reception(
    form: Any,
    user: User,
    ho: ShiftHandover,
    clear_shift_declined: Callable[[], None],
) -> None:
    if (form.get("confirm_read") or "").strip() != "1":
        raise ValueError("Debés confirmar que leíste el parte completo.")
    mode = (form.get("reception_mode") or "").strip()
    if mode not in (RECEPTION_ACCEPTED, RECEPTION_WITH_OBS):
        raise ValueError("Elegí cómo recepcionás el turno.")
    notes = (form.get("reception_notes") or "").strip()
    if mode == RECEPTION_WITH_OBS and not notes:
        raise ValueError("Las observaciones son obligatorias si elegís «Leí con observaciones».")
    lab_id, lab_err = resolve_laboratorist_from_form(
        form.get("with_laboratorist"),
        form.get("laboratorist_user_id"),
    )
    if lab_err:
        raise ValueError(lab_err)
    now_iso = now_local_iso()
    ho.incoming_user_id = user.id
    ho.received_at_iso = now_iso
    ho.reception_status = mode
    ho.reception_notes = notes if mode == RECEPTION_WITH_OBS else None
    ho.status = HANDOVER_RECEIVED
    ho.updated_at_iso = now_iso
    eff = normalize_stored_rol(user.rol)
    new_sess = ShiftSession(
        user_id=user.id,
        laboratorist_user_id=lab_id,
        effective_role=eff,
        started_at_iso=now_iso,
        ended_at_iso=None,
        status=STATUS_OPEN,
        created_at_iso=now_iso,
        updated_at_iso=now_iso,
    )
    db.session.add(new_sess)
    clear_shift_declined()
    db.session.commit()


SESSION_KEY_SHIFT_NOTIF_LAST_SEEN_ID = "shift_handover_notif_last_seen_id"


def _truncate_observation_text(text: str, max_len: int = 220) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def list_shift_observation_notifications(limit: int = 25) -> list[dict[str, Any]]:
    """
    Partes de cambio de turno con observaciones de cierre y/o de recepción (más recientes primero).
    """
    rows = list_handovers_for_history(max(limit * 4, 40))
    items: list[dict[str, Any]] = []
    for h in rows:
        closing = (h.closing_notes or "").strip()
        reception = (h.reception_notes or "").strip()
        if not closing and not reception:
            continue
        out_u = db.session.get(User, int(h.outgoing_user_id))
        in_u = db.session.get(User, int(h.incoming_user_id)) if h.incoming_user_id else None
        sess_h = h.shift_session
        outgoing_label = format_shift_operator_display(sess_h) if sess_h else (
            user_display_name(out_u) or (out_u.username if out_u else "")
        )
        incoming_label = user_display_name(in_u) or (in_u.username if in_u else "—")
        is_pending = h.status == HANDOVER_PENDING
        items.append(
            {
                "id": int(h.id),
                "handed_over_at_iso": h.handed_over_at_iso,
                "received_at_iso": h.received_at_iso,
                "outgoing_label": outgoing_label,
                "incoming_label": incoming_label,
                "status": h.status,
                "is_pending": is_pending,
                "closing_notes": _truncate_observation_text(closing),
                "reception_notes": _truncate_observation_text(reception),
                "has_closing_notes": bool(closing),
                "has_reception_notes": bool(reception),
            }
        )
        if len(items) >= limit:
            break
    return items


def shift_observation_notifications_nav(
    session: Any,
    *,
    limit: int = 25,
) -> dict[str, Any]:
    """Datos para campana de notificaciones en la barra superior."""
    items = list_shift_observation_notifications(limit)
    try:
        last_seen = int(session.get(SESSION_KEY_SHIFT_NOTIF_LAST_SEEN_ID) or 0)
    except (TypeError, ValueError):
        last_seen = 0
    unread_count = sum(1 for it in items if int(it["id"]) > last_seen)
    max_id = max((int(it["id"]) for it in items), default=last_seen)
    return {
        "items": items,
        "unread_count": unread_count,
        "last_seen_id": last_seen,
        "max_id": max_id,
    }


def mark_shift_observation_notifications_seen(session: Any, up_to_id: int | None = None) -> None:
    """Marca como vistas las notificaciones hasta el id indicado (o el más reciente en lista)."""
    if up_to_id is not None:
        new_id = int(up_to_id)
    else:
        items = list_shift_observation_notifications(1)
        new_id = int(items[0]["id"]) if items else 0
    try:
        prev = int(session.get(SESSION_KEY_SHIFT_NOTIF_LAST_SEEN_ID) or 0)
    except (TypeError, ValueError):
        prev = 0
    session[SESSION_KEY_SHIFT_NOTIF_LAST_SEEN_ID] = max(prev, new_id)


def summarize_handovers_for_history_view(limit: int = 200) -> list[dict[str, Any]]:
    rows = list_handovers_for_history(limit)
    summaries: list[dict[str, Any]] = []
    for h in rows:
        out_u = db.session.get(User, h.outgoing_user_id)
        in_u = db.session.get(User, h.incoming_user_id) if h.incoming_user_id else None
        sess_h = h.shift_session
        outgoing_label = format_shift_operator_display(sess_h) if sess_h else (
            user_display_name(out_u) or (out_u.username if out_u else "")
        )
        summaries.append(
            {
                "id": h.id,
                "handed_over_at_iso": h.handed_over_at_iso,
                "received_at_iso": h.received_at_iso,
                "outgoing": outgoing_label,
                "incoming": user_display_name(in_u) or (in_u.username if in_u else "—"),
                "status": h.status,
                "hypochlorite_stock_liters": h.hypochlorite_stock_liters,
                "reception_status": h.reception_status,
            }
        )
    return summaries
