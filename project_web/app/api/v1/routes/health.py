from __future__ import annotations

from flask import jsonify

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_PUBLIC_LIGHT
from app.extensions import limiter


@bp.get("/health")
@limiter.limit(LIMIT_PUBLIC_LIGHT)
def health():
    """Estado del servicio (monitoreo, load balancers, clientes offline)."""
    return jsonify({"ok": True, "service": "qdv_web"})
