from __future__ import annotations

from datetime import datetime

from flask import Blueprint, render_template, request

from app.auth_utils import login_required, permission_required
from app.services import produccion_graficos_service as graficos_svc
from app.web.modules.agua.routes import register_agua_routes
from app.web.modules.bolson.routes import register_bolson_routes
from app.web.modules.lab.routes import register_lab_reagents_routes
from app.web.modules.produccion.hub_routes import register_produccion_hub_routes
from app.web.modules.produccion.operativa_context import now_local
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
        salmuera_vars=request.args.getlist("salmuera_vars"),
        salmuera_vars_csv=(request.args.get("salmuera_vars_csv") or "").strip() or None,
        agua_vars=request.args.getlist("agua_vars"),
        agua_vars_csv=(request.args.get("agua_vars_csv") or "").strip() or None,
    )
    return render_template("produccion/graficos.html", **ctx)


register_produccion_hub_routes(bp)
register_stock_routes(bp)
register_salmuera_routes(bp)
register_agua_routes(bp)
register_reactor_routes(bp)
register_bolson_routes(bp)
register_lab_reagents_routes(bp)
