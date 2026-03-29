from __future__ import annotations

from flask import Blueprint, render_template

from app.auth_utils import login_required

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")
