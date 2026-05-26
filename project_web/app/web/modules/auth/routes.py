from __future__ import annotations

import time

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash

from app.auth_utils import current_user, set_session_for_user
from app.extensions import limiter
from app.repositories.user_repository import user_repo
from app.security_http import request_path_for_login_next, safe_internal_redirect_target
from app.services import security_audit_service as saudit
from app.services import shift_handover_service as sh
from app.user_roles import ROLE_LABORATORISTA, normalize_stored_rol

bp = Blueprint("auth", __name__, url_prefix="")


def _login_bucket_key() -> str:
    return "login_ip:" + (get_remote_address() or "unknown")


def _login_limits_exempt() -> bool:
    try:
        return bool(not current_app.config.get("LOGIN_RATELIMIT_ENABLED", True))
    except RuntimeError:
        return True


def _combined_login_rate_limits() -> str:
    try:
        m = current_app.config.get("LOGIN_RATELIMIT_MINUTE") or "12 per minute"
        h = current_app.config.get("LOGIN_RATELIMIT_HOUR") or "80 per hour"
        return f"{m};{h}"
    except RuntimeError:
        return "1000 per minute"


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(
    _combined_login_rate_limits,
    methods=["POST"],
    key_func=_login_bucket_key,
    exempt_when=_login_limits_exempt,
    error_message=(
        "Demasiados intentos de inicio de sesión desde esta conexión. Probá más tarde o pedí ayuda al administrador."
    ),
)
def login():
    if session.get("user_id"):
        u = current_user()
        if u is None or not u.activo:
            session.clear()
        else:
            safe_next = safe_internal_redirect_target(request.args.get("next"))
            if safe_next:
                return redirect(safe_next)
            return redirect(url_for("main.dashboard"))

    error: str | None = None
    safe_next_display = safe_internal_redirect_target(request.args.get("next")) or ""

    if request.method == "POST":
        raw_user = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        next_raw = request.form.get("next") or request.args.get("next") or ""

        next_path = safe_internal_redirect_target(next_raw)

        if not raw_user or not password:
            error = "Usuario y contraseña son obligatorios."
            saudit.record_event(
                action="login_fail",
                module="auth",
                actor_username=raw_user[:128] if raw_user else None,
                detail="credenciales_vacías",
            )
        else:
            user = user_repo.find_active_by_username_ci(raw_user)
            if user is None or not user.activo:
                error = "Usuario o contraseña incorrectos."
                saudit.record_event(
                    action="login_fail",
                    module="auth",
                    actor_username=raw_user[:128],
                    detail="usuario_desconocido_o_inactivo",
                )
            elif not check_password_hash(user.password_hash, password):
                error = "Usuario o contraseña incorrectos."
                saudit.record_event(
                    action="login_fail",
                    module="auth",
                    actor_username=raw_user[:128],
                    detail="contraseña_incorrecta",
                )
            elif normalize_stored_rol(getattr(user, "rol", None)) == ROLE_LABORATORISTA:
                error = (
                    "El perfil laboratorista no utiliza el acceso web: en planta acompañá al operador "
                    "responsable; tu participación queda registrada en el marco de su turno."
                )
                saudit.record_event(action="login_fail", module="auth", actor_username=raw_user[:128], detail="rol_lab_web_denegado")
            else:
                session.clear()
                set_session_for_user(user)
                session["_activity_ts"] = time.time()
                session.modified = True
                session.pop(sh.SESSION_KEY_SHIFT_DECLINED, None)
                saudit.record_event(action="login_ok", module="auth", actor=user, entity_type="user", entity_id=int(user.id))
                if sh.user_participates_operational_shift(user):
                    nu = next_path or ""
                    return redirect(url_for("shift.post_login", next=nu))
                if next_path:
                    return redirect(next_path)
                return redirect(url_for("main.dashboard"))

    return render_template(
        "login.html",
        error=error,
        next=safe_next_display,
    )


@bp.route("/logout", methods=["POST"])
def logout():
    u = current_user()
    if u is not None:
        saudit.record_event(action="logout", module="auth", actor=u, entity_type="user", entity_id=int(u.id))
    if u is not None and sh.user_participates_operational_shift(u) and sh.user_has_open_shift(u):
        return redirect(url_for("shift.logout_ask_leave_shift"))
    session.clear()
    return redirect(url_for("main.index"))
