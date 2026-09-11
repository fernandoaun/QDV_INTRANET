from __future__ import annotations

from flask import jsonify

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_DASHBOARD
from app.auth_utils import current_user, user_can
from app.extensions import db, limiter
from app.models import AguaRegistro, ReactorRegistro
from app.services import dashboard_service
from app.web.modules.produccion.agua_helpers import agua_row_to_dict
from app.web.modules.produccion.reactor_helpers import reactor_row_to_dict
from sqlalchemy import select


@bp.get("/produccion/reactor/ultimo")
@limiter.limit(LIMIT_DASHBOARD)
def api_reactor_ultimo():
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    if not user_can(u, "reactor"):
        return jsonify({"error": "forbidden"}), 403
    row = db.session.scalars(
        select(ReactorRegistro).order_by(ReactorRegistro.created_at_iso.desc(), ReactorRegistro.id.desc()).limit(1)
    ).first()
    return jsonify({"item": None if row is None else reactor_row_to_dict(row)})


@bp.get("/produccion/agua/ultimo")
@limiter.limit(LIMIT_DASHBOARD)
def api_agua_ultimo():
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    if not user_can(u, "agua"):
        return jsonify({"error": "forbidden"}), 403
    row = db.session.scalars(
        select(AguaRegistro).order_by(AguaRegistro.created_at_iso.desc(), AguaRegistro.id.desc()).limit(1)
    ).first()
    return jsonify({"item": None if row is None else agua_row_to_dict(row)})


@bp.get("/produccion/salmuera/ultimos")
@limiter.limit(LIMIT_DASHBOARD)
def api_salmuera_ultimos():
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    if not user_can(u, "salmuera"):
        return jsonify({"error": "forbidden"}), 403
    return jsonify({"items": dashboard_service.ultimos_hipoclorito_por_rectificador(20)})
