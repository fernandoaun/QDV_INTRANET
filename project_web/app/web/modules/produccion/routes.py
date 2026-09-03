from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from app.auth_utils import login_required, permission_required
from app.constants import ANALYSIS_INTERVAL_SECONDS, AGUA_ANALYSIS_INTERVAL_SECONDS, FILTRO_LAVADO_INTERVAL_SECONDS
from app.services import produccion_graficos_service as graficos_svc
from app.web.modules.agua.routes import register_agua_routes
from app.web.modules.bolson.routes import register_bolson_routes
from app.web.modules.lab.routes import register_lab_reagents_routes
from app.web.modules.produccion.hub_routes import register_produccion_hub_routes
from app.web.modules.produccion.operativa_context import now_local
from app.web.modules.produccion.plant_stop_routes import register_plant_stop_routes
from app.web.modules.reactor.routes import register_reactor_routes
from app.web.modules.salmuera.routes import register_salmuera_routes
from app.web.modules.stock.routes import register_stock_routes

bp = Blueprint("produccion", __name__, url_prefix="/produccion")


@bp.get("/graficos")
@login_required
@permission_required("graficos")
def graficos():
    desde = (request.args.get("desde") or datetime.now().strftime("%Y-%m-%d")).strip()
    ctx = graficos_svc.build_graficos_template_context(
        desde=desde,
        dia_arg=(request.args.get("dia") or "").strip(),
        hipo_vars=request.args.getlist("hipo_vars"),
        hipo_vars_csv=(request.args.get("hipo_vars_csv") or "").strip() or None,
        hipo_electrolizador=(request.args.get("hipo_electrolizador") or "").strip() or None,
        salmuera_vars=request.args.getlist("salmuera_vars"),
        salmuera_vars_csv=(request.args.get("salmuera_vars_csv") or "").strip() or None,
        agua_vars=request.args.getlist("agua_vars"),
        agua_vars_csv=(request.args.get("agua_vars_csv") or "").strip() or None,
    )
    return render_template("produccion/graficos.html", **ctx)


@bp.get("/cronometros/estado")
@login_required
def cronometros_estado():
    """Devuelve el estado de todos los cronómetros de producción (para alerta global de vencimiento)."""
    from app.services import plant_stop_service as ps
    from app.services import filtro_lavado_service as filtro_svc
    from app.services import salmuera_analisis_8hs_service as a8_svc
    from app.web.modules.produccion.salmuera_helpers import last_salmuera_created_at_iso_for_electrolizador_and_date
    from app.web.modules.produccion.reactor_helpers import last_reactor_created_at_iso_for_date
    from app.web.modules.produccion.agua_helpers import last_agua_created_at_iso

    fecha = ps.today_operacion_iso()
    timers: list[dict] = []

    for eid in (2, 3):
        ck = ps.circuit_key_for_electrolizador(eid)
        anchor = last_salmuera_created_at_iso_for_electrolizador_and_date(fecha, eid)
        rem = ps.compute_remaining_seconds(anchor, int(ANALYSIS_INTERVAL_SECONDS), ck, fecha_iso=fecha)
        active = ps.get_active_stop(ck) is not None
        timers.append({"key": ck, "label": f"Electrolizador {eid}", "remaining": rem, "paused": active})

    anchor_r = last_reactor_created_at_iso_for_date(fecha)
    rem_r = ps.compute_remaining_seconds(anchor_r, int(ANALYSIS_INTERVAL_SECONDS), ps.CIRCUIT_REACTOR, fecha_iso=fecha)
    active_r = ps.get_active_stop(ps.CIRCUIT_REACTOR) is not None
    timers.append({"key": ps.CIRCUIT_REACTOR, "label": "Reactor", "remaining": rem_r, "paused": active_r})

    anchor_a = last_agua_created_at_iso()
    rem_a = ps.compute_remaining_seconds(anchor_a, int(AGUA_ANALYSIS_INTERVAL_SECONDS), ps.CIRCUIT_AGUA, fecha_iso=fecha)
    active_a = ps.get_active_stop(ps.CIRCUIT_AGUA) is not None
    timers.append({"key": ps.CIRCUIT_AGUA, "label": "Agua", "remaining": rem_a, "paused": active_a})

    anchor_f = filtro_svc.last_filtro_created_at_iso()
    rem_f = ps.compute_remaining_seconds(anchor_f, int(FILTRO_LAVADO_INTERVAL_SECONDS), ps.CIRCUIT_FILTRO, fecha_iso=fecha)
    active_f = ps.get_active_stop(ps.CIRCUIT_FILTRO) is not None
    timers.append({"key": ps.CIRCUIT_FILTRO, "label": "Filtro", "remaining": rem_f, "paused": active_f})

    row_8h = a8_svc.latest_row()
    anchor_8 = (row_8h.fecha_hora_iso or row_8h.created_at_iso) if row_8h else None
    rem_8 = ps.compute_remaining_seconds(anchor_8, int(a8_svc.ANALISIS_8HS_INTERVAL_SECONDS), ps.CIRCUIT_REACTOR, fecha_iso=fecha)
    timers.append({"key": "analisis_8hs", "label": "Análisis 8 hs", "remaining": rem_8, "paused": active_r})

    overdue = [t for t in timers if t["remaining"] < 0 and not t["paused"]]
    return jsonify({"ok": True, "timers": timers, "overdue": overdue})


register_produccion_hub_routes(bp)
register_plant_stop_routes(bp)
register_stock_routes(bp)
register_salmuera_routes(bp)
register_agua_routes(bp)
register_reactor_routes(bp)
register_bolson_routes(bp)
register_lab_reagents_routes(bp)
