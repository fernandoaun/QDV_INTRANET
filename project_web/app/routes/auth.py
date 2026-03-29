from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for
from sqlalchemy import func as sa_func
from sqlalchemy import select
from werkzeug.security import check_password_hash

from app.auth_utils import set_session_for_user
from app.extensions import db
from app.models import User

bp = Blueprint("auth", __name__, url_prefix="")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("main.dashboard"))

    error: str | None = None
    if request.method == "POST":
        raw_user = (request.form.get("username") or "").strip()
        # Quitar espacios al inicio/final por copiar/pegar desde la consola
        password = (request.form.get("password") or "").strip()
        next_url = request.form.get("next") or request.args.get("next") or ""

        if not raw_user or not password:
            error = "Usuario y contraseña son obligatorios."
        else:
            key = raw_user.lower()
            user = db.session.execute(
                select(User).where(sa_func.lower(User.username) == key)
            ).scalar_one_or_none()
            if user is None or not user.activo:
                error = "Usuario o contraseña incorrectos."
            elif not check_password_hash(user.password_hash, password):
                error = "Usuario o contraseña incorrectos."
            else:
                session.clear()
                set_session_for_user(user)
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
    session.clear()
    return redirect(url_for("main.index"))
