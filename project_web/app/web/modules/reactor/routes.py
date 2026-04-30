"""Circuito reactor: rutas en el blueprint `produccion`."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from app.auth_utils import current_user, login_required, permission_required
from app.constants import ANALYSIS_INTERVAL_SECONDS, MODULE_LABELS
from app.extensions import db
from app.models import ReactorRegistro
from app.services.analysis_ref_pdf import REACTOR_ANALYSIS_REF_SPECS, analysis_ref_ui_rows
from app.web.modules.produccion.operadores_query import list_operadores_planta
from app.web.modules.produccion.operativa_context import (
    compute_turno_from_hour,
    default_operador_for_salmuera,
    now_local,
    operador_display_line,
)
from app.web.modules.produccion.reactor_helpers import (
    last_reactor_created_at_iso_for_date,
    next_reactor_lote,
    reactor_row_to_dict,
)


def register_reactor_routes(bp: Blueprint) -> None:
    @bp.route("/reactor", methods=["GET", "POST"])
    @login_required
    @permission_required("reactor")
    def reactor():
        now_for_defaults = now_local()
        fecha = (request.values.get("fecha") or now_for_defaults.strftime("%Y-%m-%d")).strip()
        turno_sugerido = compute_turno_from_hour(now_for_defaults.strftime("%H:%M"))
        operador_sugerido = default_operador_for_salmuera()
        if request.method == "POST":
            try:
                now = now_local()
                lote = next_reactor_lote(fecha)
                ph = float((request.form.get("ph") or "0").replace(",", "."))
                temperatura = float((request.form.get("temperatura") or "0").replace(",", "."))
                densidad = float((request.form.get("densidad") or "0").replace(",", "."))
                concentracion_tabla = float((request.form.get("concentracion_tabla") or "0").replace(",", "."))
                exceso_naoh = float((request.form.get("exceso_naoh") or "0").replace(",", "."))
                exceso_na2co3 = float((request.form.get("exceso_na2co3") or "0").replace(",", "."))
                operador_auto = default_operador_for_salmuera()
                db.session.add(
                    ReactorRegistro(
                        fecha_iso=fecha,
                        hora_hm=now.strftime("%H:%M"),
                        operador=operador_auto,
                        lote=lote,
                        ph=ph,
                        temperatura=temperatura,
                        densidad=densidad,
                        concentracion_tabla=concentracion_tabla,
                        exceso_naoh=exceso_naoh,
                        exceso_na2co3=exceso_na2co3,
                        observaciones=(request.form.get("observaciones") or "").strip(),
                        created_at_iso=now.isoformat(timespec="seconds"),
                    )
                )
                db.session.commit()
                flash("Registro reactor guardado.", "success")
                return redirect(url_for("produccion.reactor", fecha=fecha))
            except Exception as e:
                db.session.rollback()
                flash(str(e), "danger")

        rows = db.session.scalars(
            select(ReactorRegistro)
            .where(ReactorRegistro.fecha_iso == fecha)
            .order_by(ReactorRegistro.created_at_iso.desc(), ReactorRegistro.id.desc())
        ).all()
        analysis_ref_rows_reactor = analysis_ref_ui_rows(REACTOR_ANALYSIS_REF_SPECS)
        analysis_ref_map_reactor = {r["doc_key"]: r for r in analysis_ref_rows_reactor}
        return render_template(
            "produccion/reactor.html",
            fecha=fecha,
            registros=[reactor_row_to_dict(r) for r in rows],
            operadores=list_operadores_planta(),
            module_title=MODULE_LABELS["reactor"],
            username=current_user().username if current_user() else "",
            operador_sugerido=operador_sugerido,
            operador_display_line=operador_display_line(),
            turno_sugerido=turno_sugerido,
            server_now_iso=now_for_defaults.isoformat(timespec="seconds"),
            last_created_at_iso=last_reactor_created_at_iso_for_date(fecha),
            analysis_interval_seconds=int(ANALYSIS_INTERVAL_SECONDS),
            analysis_ref_rows_reactor=analysis_ref_rows_reactor,
            analysis_ref_map_reactor=analysis_ref_map_reactor,
        )

    @bp.get("/reactor/historial")
    @login_required
    @permission_required("reactor")
    def reactor_historial():
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()

        q = select(ReactorRegistro)
        if desde:
            q = q.where(ReactorRegistro.fecha_iso >= desde)
        if hasta:
            q = q.where(ReactorRegistro.fecha_iso <= hasta)
        if desde and hasta and desde > hasta:
            flash("Rango de fechas inválido: 'desde' no puede ser mayor que 'hasta'.", "warning")
            q = select(ReactorRegistro).where(
                ReactorRegistro.fecha_iso >= hasta,
                ReactorRegistro.fecha_iso <= desde,
            )
            desde, hasta = hasta, desde

        rows = db.session.scalars(
            q.order_by(
                ReactorRegistro.fecha_iso.desc(),
                ReactorRegistro.created_at_iso.desc(),
                ReactorRegistro.id.desc(),
            ).limit(1000)
        ).all()
        return render_template(
            "produccion/reactor_historial.html",
            desde=desde,
            hasta=hasta,
            registros=[reactor_row_to_dict(r) for r in rows],
            module_title=MODULE_LABELS["reactor"],
        )

