from __future__ import annotations

from flask import jsonify

from app.api.v1.blueprint import bp


@bp.get("/health")
def health():
    """Estado del servicio (monitoreo, load balancers, clientes offline)."""
    return jsonify({"ok": True, "service": "qdv_web"})
