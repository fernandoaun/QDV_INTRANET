from __future__ import annotations

from flask import jsonify

from app.api.v1.blueprint import bp
from app.api.v1.limits import LIMIT_SHIFT_STATUS
from app.auth_utils import current_user, perm_sets_for_user
from app.extensions import limiter
from app.services.whatsapp_write_service import capabilities


@bp.get("/me")
@limiter.limit(LIMIT_SHIFT_STATUS)
def api_me():
    u = current_user()
    if u is None:
        return jsonify({"error": "unauthorized"}), 401
    view, edit = perm_sets_for_user(u)
    from flask import g

    caps = capabilities(u)
    return jsonify(
        {
            "id": u.id,
            "username": u.username,
            "nombre_completo": u.nombre_completo or "",
            "rol": u.rol,
            "whatsapp_e164": u.whatsapp_e164 or "",
            "channel": getattr(g, "_qdv_api_channel", None),
            "perms_view": list(view),
            "perms_edit": list(edit),
            **caps,
        }
    )
