from __future__ import annotations

from flask import Blueprint, render_template

from app.auth_utils import current_user, login_required, permission_required
from app.services import dashboard_service

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/dashboard")
@login_required
def dashboard():
    ctx = dashboard_service.build_dashboard_template_context(current_user())
    return render_template("dashboard.html", **ctx)


@bp.get("/manual")
@login_required
@permission_required("manual")
def manual():
    return render_template("manual.html")
