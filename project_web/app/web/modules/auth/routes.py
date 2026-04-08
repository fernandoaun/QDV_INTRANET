from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from app.auth_utils import current_user, set_session_for_user
from app.repositories.user_repository import user_repo
from app.services import shift_handover_service as sh
from app.user_roles import ROLE_LABORATORISTA, normalize_stored_rol

bp = Blueprint("auth", __name__, url_prefix="")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("main.dashboard"))

    error: str | None = None
    if request.method == "POST":
        raw_user = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        next_url = request.form.get("next") or request.args.get("next") or ""

        if not raw_user or not password:
            error = "Usuario y contraseña son obligatorios."
        else:
            user = user_repo.find_active_by_username_ci(raw_user)
            if user is None or not user.activo:
                error = "Usuario o contraseña incorrectos."
            elif not check_password_hash(user.password_hash, password):
                error = "Usuario o contraseña incorrectos."
            elif normalize_stored_rol(getattr(user, "rol", None)) == ROLE_LABORATORISTA:
                error = (
                    "El perfil laboratorista no utiliza el acceso web: en planta acompañá al operador "
                    "responsable; tu participación queda registrada en el marco de su turno."
                )
            else:
                session.clear()
                set_session_for_user(user)
                session.pop(sh.SESSION_KEY_SHIFT_DECLINED, None)
                if sh.user_participates_operational_shift(user):
                    nu = next_url if next_url.startswith("/") else ""
                    return redirect(url_for("shift.post_login", next=nu))
                if next_url.startswith("/"):
                    return redirect(next_url)
                return redirect(url_for("main.dashboard"))

    return render_template(
        "login.html",
        error=error,
        next=(request.args.get("next") or ""),
    )


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    u = current_user()
    if u is not None and sh.user_participates_operational_shift(u) and sh.user_has_open_shift(u):
        return redirect(url_for("shift.logout_ask_leave_shift"))
    session.clear()
    return redirect(url_for("main.index"))
