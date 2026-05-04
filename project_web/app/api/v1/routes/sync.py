from __future__ import annotations

from flask import jsonify

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_PUBLIC_LIGHT
from app.extensions import limiter
from app.services.sync_meta_service import build_sync_meta


@bp.get("/sync/meta")
@limiter.limit(LIMIT_PUBLIC_LIGHT)
def sync_meta():
    """
    Metadatos mínimos para clientes offline / PWA futuros.
    Contrato estable: versión de API y tiempo de servidor (UTC).
    Los deltas y colas de outbox se agregarán sin romper este endpoint.
    """
    return jsonify(build_sync_meta())
