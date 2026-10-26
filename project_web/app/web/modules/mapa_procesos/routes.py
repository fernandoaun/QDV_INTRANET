from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, url_for

from app.auth_utils import current_user, login_required, user_can_access_sgi
from app.services import mapa_procesos_service as svc

bp = Blueprint("mapa_procesos", __name__, url_prefix="/sgi/mapa-procesos")


@bp.get("/")
@login_required
def hub():
    if not user_can_access_sgi(current_user()):
        flash("No tenés permiso para ver el mapa de procesos.", "warning")
        return redirect(url_for("main.dashboard"))
    return render_template("mapa_procesos/mapa.html", **svc.contexto())
