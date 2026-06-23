"""Paradas de planta: pausa de cronómetro, correo oculto y trazabilidad en cambio de turno."""
from __future__ import annotations

import html as html_lib
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import PlantStopAlertEmail, PlantStopEvent, User
from app.services.deadline_alert_email_service import normalize_validate_email
from app.services.mail_service import enviar_mail, is_mail_fully_configured

log = logging.getLogger(__name__)

CIRCUIT_SALMUERA_E2 = "salmuera_e2"
CIRCUIT_SALMUERA_E3 = "salmuera_e3"
CIRCUIT_REACTOR = "reactor"
CIRCUIT_AGUA = "agua"

CIRCUIT_LABELS: dict[str, str] = {
    CIRCUIT_SALMUERA_E2: "Electrolizador 2",
    CIRCUIT_SALMUERA_E3: "Electrolizador 3",
    CIRCUIT_REACTOR: "Circuito de salmuera",
    CIRCUIT_AGUA: "Circuito de agua",
}

VALID_CIRCUIT_KEYS = frozenset(CIRCUIT_LABELS.keys())

MAX_OBSERVACIONES_LEN = 500


def now_local_iso() -> str:
    from app.utils.datetime_operacion import now_operacion_local_iso_seconds

    return now_operacion_local_iso_seconds()


def today_operacion_iso() -> str:
    from app.utils.datetime_operacion import now_operacion_naive_local

    return now_operacion_naive_local().date().isoformat()


def is_fecha_operativa_actual(fecha_iso: str | None) -> bool:
    """True si la fecha de planilla coincide con el día operativo actual."""
    return (fecha_iso or today_operacion_iso()).strip() == today_operacion_iso()


def circuit_key_for_electrolizador(electrolizador: int) -> str:
    e = int(electrolizador)
    if e == 2:
        return CIRCUIT_SALMUERA_E2
    if e == 3:
        return CIRCUIT_SALMUERA_E3
    raise ValueError("Electrolizador no configurado para parada de planta.")


def circuit_label(circuit_key: str) -> str:
    return CIRCUIT_LABELS.get(circuit_key, circuit_key)


def _parse_iso(iso: str) -> datetime:
    s = (iso or "").strip()
    if not s:
        raise ValueError("fecha vacía")
    if "T" in s:
        return datetime.fromisoformat(s.replace("Z", "+00:00")[:26])
    return datetime.fromisoformat(s.replace(" ", "T")[:26])


def list_alert_emails_ordered() -> list[PlantStopAlertEmail]:
    return list(db.session.scalars(select(PlantStopAlertEmail).order_by(PlantStopAlertEmail.email)).all())


def merged_plant_stop_recipients(app: Any) -> list[str]:
    db_addrs = [str(r.email).strip().lower() for r in list_alert_emails_ordered()]
    env_addrs = [str(e).strip().lower() for e in (app.config.get("PLANT_STOP_ALERT_EMAIL_TO") or []) if str(e).strip()]
    seen: set[str] = set()
    out: list[str] = []
    for raw in db_addrs + env_addrs:
        if raw and raw not in seen:
            seen.add(raw)
            out.append(raw)
    return sorted(out)


def add_alert_email(raw: str | None) -> tuple[bool, str]:
    norm = normalize_validate_email(raw)
    if norm is None:
        return False, "Ingresá un correo electrónico válido."
    exists = db.session.scalar(select(PlantStopAlertEmail.id).where(PlantStopAlertEmail.email == norm))
    if exists is not None:
        return False, "Ese correo ya está en la lista."
    db.session.add(PlantStopAlertEmail(email=norm))
    db.session.commit()
    return True, "Correo de paradas de planta guardado."


def delete_alert_email_row(row_id: int) -> str | None:
    row = db.session.get(PlantStopAlertEmail, int(row_id))
    if row is None:
        return None
    em = row.email
    db.session.delete(row)
    db.session.commit()
    return em


def get_active_stop(circuit_key: str) -> PlantStopEvent | None:
    key = (circuit_key or "").strip()
    if key not in VALID_CIRCUIT_KEYS:
        return None
    return db.session.scalar(
        select(PlantStopEvent)
        .where(
            PlantStopEvent.circuit_key == key,
            PlantStopEvent.ended_at_iso.is_(None),
        )
        .order_by(PlantStopEvent.id.desc())
        .limit(1)
    )


def pause_seconds_after_anchor(
    anchor_iso: str | None,
    circuit_key: str,
    *,
    now_iso: str | None = None,
) -> int:
    """Segundos de parada completados desde el ancla (último análisis), sin la pausa activa."""
    key = (circuit_key or "").strip()
    if key not in VALID_CIRCUIT_KEYS:
        return 0
    anchor = (anchor_iso or "").strip()
    anchor_dt: datetime | None = _parse_iso(anchor) if anchor else None
    now_dt = _parse_iso(now_iso or now_local_iso())
    q = select(PlantStopEvent).where(
        PlantStopEvent.circuit_key == key,
        PlantStopEvent.ended_at_iso.is_not(None),
    )
    if anchor_dt is not None:
        q = q.where(PlantStopEvent.started_at_iso >= anchor)
    rows = db.session.scalars(q.order_by(PlantStopEvent.id.asc())).all()
    total = 0
    for ev in rows:
        start = _parse_iso(ev.started_at_iso)
        if anchor_dt is not None and start < anchor_dt:
            continue
        end = _parse_iso(ev.ended_at_iso or "")
        total += max(0, int((end - start).total_seconds()))
    return total


def compute_remaining_seconds(
    last_created_iso: str | None,
    interval_sec: int,
    circuit_key: str,
    *,
    fecha_iso: str | None = None,
    now_iso: str | None = None,
) -> int:
    """Segundos restantes hasta el próximo análisis (positivo) o atraso (negativo externo)."""
    now_dt = _parse_iso(now_iso or now_local_iso())
    pause_extra = pause_seconds_after_anchor(last_created_iso, circuit_key, now_iso=now_iso or now_local_iso())
    last = (last_created_iso or "").strip()
    if not last:
        return max(0, int(interval_sec))
    last_dt = _parse_iso(last)
    due_dt = last_dt.timestamp() + int(interval_sec) + pause_extra
    return int(due_dt - now_dt.timestamp())


def timer_ui_state(
    circuit_key: str,
    last_created_iso: str | None,
    interval_sec: int,
    *,
    fecha_iso: str | None = None,
) -> dict[str, Any]:
    """Estado para el cronómetro en pantalla (incluye parada activa solo en fecha operativa actual)."""
    fecha = (fecha_iso or today_operacion_iso()).strip()
    active_ev = get_active_stop(circuit_key) if is_fecha_operativa_actual(fecha) else None
    pause_extra = pause_seconds_after_anchor(last_created_iso, circuit_key)
    remaining = compute_remaining_seconds(
        last_created_iso,
        interval_sec,
        circuit_key,
        fecha_iso=fecha,
    )
    if active_ev is not None:
        frozen = active_ev.frozen_remaining_sec
        if frozen is None:
            frozen = max(0, remaining)
        return {
            "active": True,
            "started_at_iso": active_ev.started_at_iso,
            "frozen_remaining_sec": int(frozen),
            "pause_extra_seconds": pause_extra,
            "circuit_key": circuit_key,
            "circuit_label": circuit_label(circuit_key),
        }
    return {
        "active": False,
        "started_at_iso": None,
        "frozen_remaining_sec": None,
        "pause_extra_seconds": pause_extra,
        "circuit_key": circuit_key,
        "circuit_label": circuit_label(circuit_key),
    }


def event_to_dict(ev: PlantStopEvent) -> dict[str, Any]:
    ended = (ev.ended_at_iso or "").strip()
    return {
        "id": ev.id,
        "circuit_key": ev.circuit_key,
        "circuit_label": circuit_label(ev.circuit_key),
        "started_at_iso": ev.started_at_iso,
        "ended_at_iso": ended or None,
        "operador": ev.operador or "",
        "observaciones": (ev.observaciones or "").strip(),
        "motivo": (ev.observaciones or "").strip(),
        "active": not bool(ended),
    }


def _send_stop_mail(app: Any, ev: PlantStopEvent) -> None:
    recipients = merged_plant_stop_recipients(app)
    if not recipients:
        log.warning("Parada de planta id=%s: sin destinatarios PLANT_STOP_ALERT_EMAIL", ev.id)
        return
    if not is_mail_fully_configured(app):
        log.warning("Parada de planta id=%s: SMTP no configurado", ev.id)
        return
    label = circuit_label(ev.circuit_key)
    obs = (ev.observaciones or "").strip()
    obs_html = f"<p><strong>Observaciones:</strong> {html_lib.escape(obs)}</p>" if obs else ""
    obs_txt = f"\nObservaciones: {obs}" if obs else ""
    extra_8h = ""
    if ev.circuit_key == CIRCUIT_REACTOR:
        extra_8h = "<p>También se detuvo el cronómetro del <strong>análisis 8 hs</strong> (dureza / cloro libre).</p>"
    asunto = f"QDV — Parada de planta · {label}"
    cuerpo_html = (
        f"<p>Se declaró <strong>parada de planta</strong> en <strong>{html_lib.escape(label)}</strong>.</p>"
        f"{extra_8h}"
        f"<p><strong>Operador:</strong> {html_lib.escape(ev.operador or '—')}<br>"
        f"<strong>Inicio:</strong> {html_lib.escape(ev.started_at_iso)}</p>"
        f"{obs_html}"
        f"<p class=\"text-muted\">Aviso automático (no visible para el operador en pantalla).</p>"
    )
    cuerpo_texto = (
        f"Parada de planta en {label}.\n"
        f"Operador: {ev.operador or '—'}\n"
        f"Inicio: {ev.started_at_iso}{obs_txt}"
    )
    enviar_mail(
        app,
        destinatarios=recipients,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
    )
    ev.mail_sent_at_iso = now_local_iso()


def _send_resume_mail(app: Any, ev: PlantStopEvent, *, operador: str | None = None) -> None:
    recipients = merged_plant_stop_recipients(app)
    if not recipients:
        log.warning("Reanudación de análisis id=%s: sin destinatarios PLANT_STOP_ALERT_EMAIL", ev.id)
        return
    if not is_mail_fully_configured(app):
        log.warning("Reanudación de análisis id=%s: SMTP no configurado", ev.id)
        return
    label = circuit_label(ev.circuit_key)
    obs = (ev.observaciones or "").strip()
    obs_html = f"<p><strong>Observaciones de la parada:</strong> {html_lib.escape(obs)}</p>" if obs else ""
    obs_txt = f"\nObservaciones de la parada: {obs}" if obs else ""
    extra_8h = ""
    if ev.circuit_key == CIRCUIT_REACTOR:
        extra_8h = "<p>También se reanudó el cronómetro del <strong>análisis 8 hs</strong> (dureza / cloro libre).</p>"
    op_resume = (operador or "").strip() or "—"
    op_stop = (ev.operador or "").strip() or "—"
    ended = (ev.ended_at_iso or "").strip() or "—"
    asunto = f"QDV — Reanudación de análisis · {label}"
    cuerpo_html = (
        f"<p>Se <strong>reanudó el análisis</strong> en <strong>{html_lib.escape(label)}</strong> "
        f"(fin de parada de planta).</p>"
        f"{extra_8h}"
        f"<p><strong>Operador (reanudación):</strong> {html_lib.escape(op_resume)}<br>"
        f"<strong>Operador (parada):</strong> {html_lib.escape(op_stop)}<br>"
        f"<strong>Inicio parada:</strong> {html_lib.escape(ev.started_at_iso)}<br>"
        f"<strong>Fin parada:</strong> {html_lib.escape(ended)}</p>"
        f"{obs_html}"
        f"<p class=\"text-muted\">Aviso automático (no visible para el operador en pantalla).</p>"
    )
    cuerpo_texto = (
        f"Reanudación de análisis en {label} (fin de parada de planta).\n"
        f"Operador (reanudación): {op_resume}\n"
        f"Operador (parada): {op_stop}\n"
        f"Inicio parada: {ev.started_at_iso}\n"
        f"Fin parada: {ended}{obs_txt}"
    )
    enviar_mail(
        app,
        destinatarios=recipients,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
    )


def start_plant_stop(
    app: Any,
    *,
    circuit_key: str,
    user: User,
    operador: str,
    last_created_iso: str | None,
    interval_sec: int,
    observaciones: str | None = None,
) -> PlantStopEvent:
    key = (circuit_key or "").strip()
    if key not in VALID_CIRCUIT_KEYS:
        raise ValueError("Circuito no válido para parada de planta.")
    if get_active_stop(key) is not None:
        raise ValueError("Ya hay una parada de planta activa en este punto.")
    obs_clean = (observaciones or "").strip()
    if len(obs_clean) > MAX_OBSERVACIONES_LEN:
        raise ValueError(f"El motivo no puede superar {MAX_OBSERVACIONES_LEN} caracteres.")
    now_iso = now_local_iso()
    remaining = compute_remaining_seconds(last_created_iso, interval_sec, key)
    frozen = max(0, remaining)
    frozen_8h: int | None = None
    if key == CIRCUIT_REACTOR:
        from app.services.salmuera_analisis_8hs_service import (
            ANALISIS_8HS_INTERVAL_SECONDS,
            latest_row,
        )

        row_8h = latest_row()
        anchor_8h = (row_8h.fecha_hora_iso or row_8h.created_at_iso) if row_8h else None
        rem_8h = compute_remaining_seconds(
            anchor_8h,
            int(ANALISIS_8HS_INTERVAL_SECONDS),
            key,
        )
        frozen_8h = max(0, rem_8h)
    ev = PlantStopEvent(
        circuit_key=key,
        started_at_iso=now_iso,
        ended_at_iso=None,
        operador=(operador or user.username or "").strip()[:256],
        user_id=int(user.id) if user.id else None,
        observaciones=obs_clean or None,
        frozen_remaining_sec=frozen,
        frozen_remaining_sec_analisis8=frozen_8h,
        mail_sent_at_iso=None,
        created_at_iso=now_iso,
    )
    db.session.add(ev)
    db.session.flush()
    try:
        _send_stop_mail(app, ev)
    except Exception:
        log.exception("Fallo envío mail parada de planta id=%s", ev.id)
    db.session.commit()
    return ev


def end_plant_stop(
    app: Any,
    circuit_key: str,
    *,
    operador: str | None = None,
) -> PlantStopEvent:
    key = (circuit_key or "").strip()
    ev = get_active_stop(key)
    if ev is None:
        raise ValueError("No hay parada de planta activa en este punto.")
    ev.ended_at_iso = now_local_iso()
    db.session.flush()
    try:
        _send_resume_mail(app, ev, operador=operador)
    except Exception:
        log.exception("Fallo envío mail reanudación de análisis id=%s", ev.id)
    db.session.commit()
    return ev


def analisis8_plant_stop_overlay(
    *,
    last_fecha_hora_iso: str | None,
    interval_sec: int,
    fecha_iso: str | None = None,
) -> dict[str, Any]:
    """Estado de parada para el cronómetro de análisis 8 hs (sigue la parada del circuito reactor)."""
    pause_extra = pause_seconds_after_anchor(last_fecha_hora_iso, CIRCUIT_REACTOR)
    active_ev = get_active_stop(CIRCUIT_REACTOR) if is_fecha_operativa_actual(fecha_iso) else None
    if active_ev is None:
        return {
            "active": False,
            "started_at_iso": None,
            "frozen_remaining_sec": None,
            "pause_extra_seconds": pause_extra,
        }
    frozen = active_ev.frozen_remaining_sec_analisis8
    if frozen is None:
        frozen = max(
            0,
            compute_remaining_seconds(last_fecha_hora_iso, interval_sec, CIRCUIT_REACTOR),
        )
    return {
        "active": True,
        "started_at_iso": active_ev.started_at_iso,
        "frozen_remaining_sec": int(frozen),
        "pause_extra_seconds": pause_extra,
    }


def enrich_salmuera_timer_rows(
    rows: list[dict[str, Any]],
    fecha_iso: str,
    interval_sec: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        eid = int(row.get("electrolizador", 0))
        ck = circuit_key_for_electrolizador(eid)
        enriched = dict(row)
        enriched["plant_stop"] = timer_ui_state(
            ck,
            row.get("last_created_at_iso"),
            interval_sec,
            fecha_iso=fecha_iso,
        )
        out.append(enriched)
    return out


def list_stops_in_interval(started_at_iso: str, ended_at_iso: str) -> list[dict[str, Any]]:
    """Paradas que intersectan la ventana del turno (para entrega de turno)."""
    lo = (started_at_iso or "").strip()
    hi = (ended_at_iso or "").strip()
    if not lo or not hi:
        return []
    rows = db.session.scalars(
        select(PlantStopEvent)
        .where(
            PlantStopEvent.started_at_iso <= hi,
            (PlantStopEvent.ended_at_iso.is_(None)) | (PlantStopEvent.ended_at_iso >= lo),
        )
        .order_by(PlantStopEvent.started_at_iso.asc(), PlantStopEvent.id.asc())
    ).all()
    return [event_to_dict(r) for r in rows]
