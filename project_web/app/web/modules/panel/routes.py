from __future__ import annotations

from flask import Blueprint, render_template

from app.auth_utils import current_user, login_required, permission_required
from app.services import dashboard_service

bp = Blueprint("main", __name__)


@bp.get("/healthz")
def healthz():
    """Comprobación ligera (sin plantillas ni sesión) para Render y diagnóstico."""
    return "ok", 200


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/dashboard")
@login_required
def dashboard():
    ctx = dashboard_service.build_dashboard_template_context(current_user())
    ctx["dashboard_tab"] = "resumen"
    return render_template("dashboard.html", **ctx)


@bp.get("/dashboard/operadores")
@login_required
def dashboard_operadores():
    from app.services.operador_dashboard_service import build_operador_dashboard_context

    ctx = build_operador_dashboard_context()
    ctx["dashboard_tab"] = "operadores"
    return render_template("dashboard_operadores.html", **ctx)


@bp.get("/manual")
@login_required
@permission_required("manual")
def manual():
    return render_template("manual.html")
