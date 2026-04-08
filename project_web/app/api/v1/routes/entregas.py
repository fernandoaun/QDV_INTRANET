from __future__ import annotations

from flask import jsonify

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_HEAVY_READ
from app.auth_utils import current_user, user_can_access_entregas_hub
from app.extensions import limiter
from app.services import entregas_service


@bp.get("/entregas")
@limiter.limit(LIMIT_HEAVY_READ)
def api_list_entregas():
    """
    Listado de entregas (misma fuente que la gestión web), para panel móvil / sync.
    """
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    if not user_can_access_entregas_hub(u):
        return jsonify({"error": "forbidden"}), 403

    rows = entregas_service.listar_entregas()
    return jsonify({"items": [entregas_service.entrega_to_api_dict(e) for e in rows]})
