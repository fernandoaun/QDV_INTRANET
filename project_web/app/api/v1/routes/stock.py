from __future__ import annotations

from flask import jsonify, request

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_HEAVY_READ, LIMIT_STOCK_READ
from app.auth_utils import (
    current_user,
    user_can_access_stock_hub,
    user_can_view_stock_consumos,
    user_can_view_stock_existencias,
    user_can_view_stock_historial,
)
from app.extensions import limiter
from app.services import stock_service


@bp.get("/stock/existencias")
@limiter.limit(LIMIT_STOCK_READ)
def api_stock_existencias():
    """
    Misma lógica que Producción → Stock → Ver existencias (`stock_ver`).
    Query: categoria=todas | materia_prima | laboratorio | producto_terminado
    """
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    if not user_can_view_stock_existencias(u):
        return jsonify({"error": "forbidden"}), 403

    cat = (request.args.get("categoria") or "todas").strip()
    try:
        if cat == "todas":
            items = stock_service.stock_consolidado_todas()
        else:
            items = stock_service.stock_consolidado(cat)
    except Exception:
        items = []

    return jsonify({"categoria": cat, "items": items})


def _parse_positive_int(raw: str | None, default: int) -> int:
    try:
        return int((raw or str(default)).strip())
    except ValueError:
        return default


@bp.get("/stock/consumos/producto")
@limiter.limit(LIMIT_STOCK_READ)
def api_stock_consumos_producto():
    """
    Consumos recientes de un producto (misma lógica que la pantalla de consumo de stock).
    Query: categoria, producto (obligatorios); limit opcional (default 50, máx. 200 en servicio).
    """
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    if not user_can_view_stock_consumos(u):
        return jsonify({"error": "forbidden"}), 403

    cat = (request.args.get("categoria") or "").strip()
    prod = (request.args.get("producto") or "").strip()
    if not cat or not prod:
        return jsonify(
            {"error": "bad_request", "message": "Parámetros obligatorios: categoria y producto."}
        ), 400

    limit = _parse_positive_int(request.args.get("limit"), 50)
    try:
        items = stock_service.consumos_recientes(cat, prod, limit)
    except ValueError as e:
        return jsonify({"error": "bad_request", "message": str(e)}), 400

    return jsonify({"categoria": cat, "producto": prod, "items": items})


@bp.get("/stock/consumos/ultimos-dias")
@limiter.limit(LIMIT_HEAVY_READ)
def api_stock_consumos_ultimos_dias():
    """
    Consumos en ventana de fechas (misma idea que el resumen del hub de stock).
    Query: dias (default 30), limit (default 300).
    """
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    if not user_can_view_stock_historial(u):
        return jsonify({"error": "forbidden"}), 403

    dias = _parse_positive_int(request.args.get("dias"), 30)
    limit = _parse_positive_int(request.args.get("limit"), 300)
    items = stock_service.consumos_ultimos_dias(dias, limit)
    return jsonify({"dias": dias, "limit": limit, "items": items})


@bp.get("/stock/alertas")
@limiter.limit(LIMIT_STOCK_READ)
def api_stock_alertas():
    """
    Productos en o bajo umbral de alerta (misma fuente que el panel / dashboard).
    Requiere acceso al hub de stock, como `main.dashboard` → alertas_stock.
    Query: limit (default 100, acotado en el servicio a 1..1000).
    """
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    if not user_can_access_stock_hub(u):
        return jsonify({"error": "forbidden"}), 403

    limit = _parse_positive_int(request.args.get("limit"), 100)
    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000
    try:
        items = stock_service.alertas_bajo_stock(limit)
    except Exception:
        items = []

    return jsonify({"limit": limit, "items": items})
