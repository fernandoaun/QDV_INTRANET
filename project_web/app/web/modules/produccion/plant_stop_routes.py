"""Parada de planta: toggle JSON compartido por circuitos de producción."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from app.auth_utils import current_user, login_required, user_can
from app.constants import AGUA_ANALYSIS_INTERVAL_SECONDS, ANALYSIS_INTERVAL_SECONDS
from app.services import plant_stop_service as ps
from app.web.modules.produccion.agua_helpers import last_agua_created_at_iso_for_date
from app.web.modules.produccion.operativa_context import default_operador_for_salmuera, operador_display_line
from app.web.modules.produccion.reactor_helpers import last_reactor_created_at_iso_for_date
from app.web.modules.produccion.salmuera_helpers import last_salmuera_created_at_iso_for_electrolizador_and_date
_CIRCUIT_PERM = {
    ps.CIRCUIT_SALMUERA_E2: "salmuera",
    ps.CIRCUIT_SALMUERA_E3: "salmuera",
    ps.CIRCUIT_REACTOR: "reactor",
    ps.CIRCUIT_AGUA: "agua",
}


def _last_created_for_circuit(circuit_key: str, fecha_iso: str) -> str | None:
    if circuit_key == ps.CIRCUIT_SALMUERA_E2:
        return last_salmuera_created_at_iso_for_electrolizador_and_date(fecha_iso, 2)
    if circuit_key == ps.CIRCUIT_SALMUERA_E3:
        return last_salmuera_created_at_iso_for_electrolizador_and_date(fecha_iso, 3)
    if circuit_key == ps.CIRCUIT_REACTOR:
        return last_reactor_created_at_iso_for_date(fecha_iso)
    if circuit_key == ps.CIRCUIT_AGUA:
        return last_agua_created_at_iso_for_date(fecha_iso)
    return None


def _interval_for_circuit(circuit_key: str) -> int:
    if circuit_key == ps.CIRCUIT_AGUA:
        return int(AGUA_ANALYSIS_INTERVAL_SECONDS)
    return int(ANALYSIS_INTERVAL_SECONDS)


def register_plant_stop_routes(bp: Blueprint) -> None:
    @bp.post("/parada-planta")
    @login_required
    def parada_planta_toggle():
        u = current_user()
        if u is None:
            return jsonify({"ok": False, "error": "Sesión requerida."}), 401

        data: dict[str, Any] = request.get_json(silent=True) or {}
        circuit_key = (data.get("circuit_key") or request.form.get("circuit_key") or "").strip()
        action = (data.get("action") or request.form.get("action") or "").strip().lower()
        fecha_iso = (data.get("fecha_iso") or request.form.get("fecha_iso") or ps.today_operacion_iso()).strip()

        if circuit_key not in ps.VALID_CIRCUIT_KEYS:
            return jsonify({"ok": False, "error": "Circuito no válido."}), 400

        perm = _CIRCUIT_PERM.get(circuit_key)
        if perm and not user_can(u, perm):
            return jsonify({"ok": False, "error": "Sin permiso para este módulo."}), 403

        if action not in ("start", "end"):
            return jsonify({"ok": False, "error": "Acción no válida."}), 400

        if not ps.is_fecha_operativa_actual(fecha_iso):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "La parada de planta solo puede declararse o reanudarse en la fecha operativa de hoy.",
                    }
                ),
                400,
            )

        last_created = _last_created_for_circuit(circuit_key, fecha_iso)
        interval_sec = _interval_for_circuit(circuit_key)

        try:
            if action == "start":
                operador = operador_display_line() or default_operador_for_salmuera() or u.username
                ev = ps.start_plant_stop(
                    current_app,
                    circuit_key=circuit_key,
                    user=u,
                    operador=operador or "",
                    last_created_iso=last_created,
                    interval_sec=interval_sec,
                    observaciones=(data.get("observaciones") or request.form.get("observaciones") or "").strip() or None,
                )
                msg = f"Parada de planta registrada en {ps.circuit_label(circuit_key)}."
            else:
                ev = ps.end_plant_stop(circuit_key)
                msg = f"Análisis reanudado en {ps.circuit_label(circuit_key)}."
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        plant_stop = ps.timer_ui_state(circuit_key, last_created, interval_sec, fecha_iso=fecha_iso)
        payload: dict[str, Any] = {
            "ok": True,
            "message": msg,
            "action": action,
            "event": ps.event_to_dict(ev),
            "plant_stop": plant_stop,
        }
        if circuit_key == ps.CIRCUIT_REACTOR:
            from app.services.salmuera_analisis_8hs_service import (
                ANALISIS_8HS_INTERVAL_SECONDS,
                build_status,
                latest_row,
            )
            from app.web.modules.produccion.operativa_context import now_local

            row_8h = latest_row()
            anchor_8h = (row_8h.fecha_hora_iso or row_8h.created_at_iso) if row_8h else None
            payload["analisis8_plant_stop"] = ps.analisis8_plant_stop_overlay(
                last_fecha_hora_iso=anchor_8h,
                interval_sec=int(ANALISIS_8HS_INTERVAL_SECONDS),
                fecha_iso=fecha_iso,
            )
            payload["analisis8_status"] = build_status(now_local(), fecha_iso=fecha_iso)
        return jsonify(payload), 200
