from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import current_user, login_required, user_can_access_entregas_hub, user_can_view_stock_existencias
from app.extensions import db
from app.services import lote_produccion_service as lp
from app.services import trazabilidad_service as ts
from app.user_roles import user_is_responsable_laboratorio

bp = Blueprint("trazabilidad", __name__, url_prefix="/trazabilidad")


def puede_ver_trazabilidad(user) -> bool:
    return user_can_access_entregas_hub(user) or user_can_view_stock_existencias(user)


def puede_observar_lote(user) -> bool:
    return bool(user and (user.is_admin or user_is_responsable_laboratorio(user)))


@bp.route("/")
@login_required
def index():
    u = current_user()
    if not puede_ver_trazabilidad(u):
        abort(403)
    q = (request.args.get("q") or "").strip()
    ingreso_id = request.args.get("ingreso", type=int)
    ctx: dict = {"q": q, "factor": ts.FACTOR_PULMON, "puede_observar": puede_observar_lote(u)}
    if ingreso_id:
        ctx["rastreo"] = ts.rastrear_ingreso(ingreso_id)
        if ctx["rastreo"] is None:
            abort(404)
    elif q:
        r = ts.buscar(q)
        if r["tipo"] == "despacho":
            ctx["despacho"] = ts.detalle_lote_despacho(r["lote"])
        elif r["tipo"] == "produccion":
            ctx["produccion"] = ts.detalle_lote_produccion(r["lote"])
        elif len(r["ingresos"]) == 1:
            ctx["rastreo"] = ts.rastrear_ingreso(int(r["ingresos"][0].id))
        else:
            ctx["ingresos"] = r["ingresos"]
    return render_template("trazabilidad/index.html", **ctx)


@bp.post("/lote/<lote>/observacion")
@login_required
def observar_lote(lote: str):
    u = current_user()
    if not puede_observar_lote(u):
        abort(403)
    turno = lp.turno_de_lote(lote)
    if turno is None:
        abort(404)
    if request.form.get("accion") == "quitar":
        lp.quitar_observacion(turno)
        flash(f"Se quitó la observación del lote {turno.lote_produccion}.", "success")
    else:
        try:
            lp.marcar_observado(turno, request.form.get("nota") or "", int(u.id))
        except ValueError as ex:
            flash(str(ex), "danger")
            return redirect(url_for("trazabilidad.index", q=turno.lote_produccion))
        flash(f"Lote {turno.lote_produccion} marcado como observado.", "warning")
    db.session.commit()
    return redirect(url_for("trazabilidad.index", q=turno.lote_produccion))
