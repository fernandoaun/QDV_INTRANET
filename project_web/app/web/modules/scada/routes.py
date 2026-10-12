"""Vista de planta tipo SCADA (por ahora solo administrador)."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from app.auth_utils import admin_required
from app.services import scada_service

bp = Blueprint("scada", __name__, url_prefix="/scada")


@bp.get("/")
@admin_required
def planta():
    return render_template("scada/planta.html")


@bp.get("/estado.json")
@admin_required
def estado():
    resp = jsonify(scada_service.snapshot())
    resp.headers["Cache-Control"] = "no-store"
    return resp
