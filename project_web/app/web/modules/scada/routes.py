"""Vista de planta tipo SCADA: mismo acceso que Producción (es su versión visual)."""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, flash, jsonify, redirect, render_template, url_for

from app.auth_utils import current_user, login_required, user_can_access_production_hub
from app.services import scada_service

bp = Blueprint("scada", __name__, url_prefix="/scada")


def _acceso_produccion(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not user_can_access_production_hub(current_user()):
            flash("No tenés permiso para acceder a Producción.", "warning")
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)

    return wrapped


@bp.get("/")
@login_required
@_acceso_produccion
def planta():
    return render_template("scada/planta.html")


@bp.get("/estado.json")
@login_required
@_acceso_produccion
def estado():
    resp = jsonify(scada_service.snapshot())
    resp.headers["Cache-Control"] = "no-store"
    return resp
