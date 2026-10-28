from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from app.auth_utils import current_user, login_required, user_can_access_entregas_hub, user_can_view_stock_existencias
from app.services import trazabilidad_service as ts

bp = Blueprint("trazabilidad", __name__, url_prefix="/trazabilidad")


def puede_ver_trazabilidad(user) -> bool:
    return user_can_access_entregas_hub(user) or user_can_view_stock_existencias(user)


@bp.route("/")
@login_required
def index():
    if not puede_ver_trazabilidad(current_user()):
        abort(403)
    q = (request.args.get("q") or "").strip()
    ingreso_id = request.args.get("ingreso", type=int)
    ctx: dict = {"q": q, "factor": ts.FACTOR_PULMON}
    if ingreso_id:
        ctx["rastreo"] = ts.rastrear_ingreso(ingreso_id)
        if ctx["rastreo"] is None:
            abort(404)
    elif q:
        r = ts.buscar(q)
        if r["tipo"] == "despacho":
            ctx["despacho"] = ts.detalle_lote_despacho(r["lote"])
        elif len(r["ingresos"]) == 1:
            ctx["rastreo"] = ts.rastrear_ingreso(int(r["ingresos"][0].id))
        else:
            ctx["ingresos"] = r["ingresos"]
    return render_template("trazabilidad/index.html", **ctx)
