"""Estado de cronómetros de producción para la alerta global de vencimiento."""
from __future__ import annotations

from typing import Any

from app.constants import (
    AGUA_ANALYSIS_INTERVAL_SECONDS,
    ANALYSIS_INTERVAL_SECONDS,
    FILTRO_LAVADO_INTERVAL_SECONDS,
    SALMUERA_PANEL_ELECTROLIZADORES,
)
from app.services import filtro_lavado_service as filtro_svc
from app.services import plant_stop_service as ps
from app.services import salmuera_analisis_8hs_service as a8_svc
from app.web.modules.produccion.agua_helpers import last_agua_created_at_iso
from app.web.modules.produccion.reactor_helpers import last_reactor_created_at_iso
from app.web.modules.produccion.salmuera_helpers import last_salmuera_created_at_iso_for_electrolizador


def _status(
    *,
    key: str,
    label: str,
    last_iso: str | None,
    interval_sec: int,
    fecha: str,
    paused: bool,
) -> dict[str, Any]:
    rem = ps.compute_remaining_seconds(last_iso, int(interval_sec), key, fecha_iso=fecha)
    overdue = (not paused) and rem <= 0 and bool((last_iso or "").strip())
    return {
        "key": key,
        "label": label,
        "remaining": rem,
        "paused": paused,
        "overdue": overdue,
        "last_created_at_iso": last_iso,
    }


def list_timer_statuses() -> dict[str, Any]:
    fecha = ps.today_operacion_iso()
    timers: list[dict[str, Any]] = []

    for eid in SALMUERA_PANEL_ELECTROLIZADORES:
        ck = ps.circuit_key_for_electrolizador(int(eid))
        anchor = last_salmuera_created_at_iso_for_electrolizador(int(eid))
        paused = ps.get_active_stop(ck) is not None
        timers.append(
            _status(
                key=ck,
                label=f"Electrolizador {eid}",
                last_iso=anchor,
                interval_sec=int(ANALYSIS_INTERVAL_SECONDS),
                fecha=fecha,
                paused=paused,
            )
        )

    paused_r = ps.get_active_stop(ps.CIRCUIT_REACTOR) is not None
    timers.append(
        _status(
            key=ps.CIRCUIT_REACTOR,
            label="Reactor",
            last_iso=last_reactor_created_at_iso(),
            interval_sec=int(ANALYSIS_INTERVAL_SECONDS),
            fecha=fecha,
            paused=paused_r,
        )
    )

    timers.append(
        _status(
            key=ps.CIRCUIT_AGUA,
            label="Agua",
            last_iso=last_agua_created_at_iso(),
            interval_sec=int(AGUA_ANALYSIS_INTERVAL_SECONDS),
            fecha=fecha,
            paused=ps.get_active_stop(ps.CIRCUIT_AGUA) is not None,
        )
    )

    timers.append(
        _status(
            key=ps.CIRCUIT_FILTRO,
            label="Filtro (lavado y enjuague)",
            last_iso=filtro_svc.last_filtro_created_at_iso(),
            interval_sec=int(FILTRO_LAVADO_INTERVAL_SECONDS),
            fecha=fecha,
            paused=ps.get_active_stop(ps.CIRCUIT_FILTRO) is not None,
        )
    )

    row_8h = a8_svc.latest_row()
    anchor_8 = (row_8h.fecha_hora_iso or row_8h.created_at_iso) if row_8h else None
    rem_8 = ps.compute_remaining_seconds(
        anchor_8, int(a8_svc.ANALISIS_8HS_INTERVAL_SECONDS), ps.CIRCUIT_REACTOR, fecha_iso=fecha
    )
    timers.append(
        {
            "key": "analisis_8hs",
            "label": "Análisis 8 hs",
            "remaining": rem_8,
            "paused": paused_r,
            "overdue": (not paused_r) and bool((anchor_8 or "").strip()) and rem_8 <= 0,
            "last_created_at_iso": anchor_8,
        }
    )

    overdue = [t for t in timers if t.get("overdue")]
    return {"ok": True, "timers": timers, "overdue": overdue}
