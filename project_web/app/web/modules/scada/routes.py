"""Vista de planta tipo SCADA: mismo acceso que Producción (es su versión visual)."""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, flash, jsonify, redirect, render_template, url_for

from app.auth_utils import current_user, login_required, user_can_access_production_hub, user_can_edit
from app.extensions import db
from app.models import Equipo
from app.services import scada_service
from app.web.modules.produccion.plant_stop_routes import _CIRCUIT_PERM

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
    # Parar / poner en marcha: quien puede cargar en ese circuito (los de solo lectura no).
    u = current_user()
    puede_parar = {c: user_can_edit(u, perm) for c, perm in _CIRCUIT_PERM.items()}
    # Portafiltros de papel a cada lado de la tolva: el consumo se carga con su equipo.
    equipos = {e.nombre_equipo: e.id for e in db.session.query(Equipo).filter(Equipo.activo.is_(True))}
    portafiltros = {
        "izq": equipos.get("Tanque Salmuera Clarificada"),
        "der": equipos.get("Tolva UltraPura"),
    }
    return render_template("scada/planta.html", puede_parar=puede_parar, portafiltros=portafiltros)


@bp.get("/estado.json")
@login_required
@_acceso_produccion
def estado():
    resp = jsonify(scada_service.snapshot())
    resp.headers["Cache-Control"] = "no-store"
    return resp
