from __future__ import annotations

from flask import jsonify, session

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_SHIFT_STATUS
from app.auth_utils import current_user, user_shift_may_write_operational
from app.extensions import limiter
from app.services import shift_handover_service as sh


@bp.get("/shift/status")
@limiter.limit(LIMIT_SHIFT_STATUS)
def shift_status():
    """
    Estado de turno operativo para el usuario de sesión (misma lógica que el panel HTML).
    """
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401

    open_s = sh.get_open_shift_session()
    pending = sh.get_pending_handover()
    payload = {
        "user_id": u.id,
        "participates_operational_shift": sh.user_participates_operational_shift(u),
        "pending_handover": pending is not None,
        "open_shift": None
        if open_s is None
        else {
            "user_id": open_s.user_id,
            "operator_display": sh.format_shift_operator_display(open_s),
        },
        "may_write_operational": user_shift_may_write_operational(u, session),
    }
    return jsonify(payload)
