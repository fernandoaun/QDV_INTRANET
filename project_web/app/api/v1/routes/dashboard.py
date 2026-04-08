from __future__ import annotations

from flask import jsonify

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_DASHBOARD
from app.auth_utils import current_user, user_can, user_can_access_stock_hub
from app.extensions import limiter
from app.services import dashboard_service, stock_service


@bp.get("/dashboard/snapshot")
@limiter.limit(LIMIT_DASHBOARD)
def api_dashboard_snapshot():
    """
    Resumen alineado con `main.dashboard`: solo incluye bloques permitidos para el usuario.
    """
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401

    out: dict = {}

    if user_can_access_stock_hub(u):
        try:
            out["alertas_stock"] = stock_service.alertas_bajo_stock(30)
        except Exception:
            out["alertas_stock"] = []
        try:
            out["ultimos_consumos_materia_prima"] = dashboard_service.ultimos_consumos_por_materia_prima(50)
        except Exception:
            out["ultimos_consumos_materia_prima"] = []

    if u.is_admin or user_can(u, "salmuera"):
        try:
            out["ultimos_hipoclorito_por_rectificador"] = dashboard_service.ultimos_hipoclorito_por_rectificador(30)
        except Exception:
            out["ultimos_hipoclorito_por_rectificador"] = []

    if u.is_admin or user_can(u, "reactor"):
        try:
            out["ultimo_registro_reactor_salmuera"] = dashboard_service.ultimo_registro_salmuera()
        except Exception:
            out["ultimo_registro_reactor_salmuera"] = None

    if u.is_admin or user_can(u, "agua"):
        try:
            out["ultimo_registro_agua"] = dashboard_service.ultimo_registro_agua()
        except Exception:
            out["ultimo_registro_agua"] = None

    return jsonify(out)
