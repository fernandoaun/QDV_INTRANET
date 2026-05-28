"""Circuito de agua y columnas: rutas en el blueprint `produccion`."""

from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from app.auth_utils import current_user, login_required, permission_required
from app.constants import AGUA_ANALYSIS_INTERVAL_SECONDS, MODULE_LABELS
from app.extensions import db
from app.models import AguaRegistro
from app.services.analysis_ref_pdf import AGUA_ANALYSIS_REF_SPECS, analysis_ref_ui_rows
from app.web.modules.produccion.agua_helpers import (
    agua_row_to_dict,
    columnas_latest_dict,
    columnas_semaforo_global,
    last_agua_created_at_iso_for_date,
    next_agua_lote,
    redirect_agua_columnas_anchor,
    save_columna_intercambio_from_form,
)
from app.web.modules.produccion.operativa_context import (
    compute_turno_from_hour,
    default_operador_for_salmuera,
    now_local,
    operador_display_line,
)


def register_agua_routes(bp: Blueprint) -> None:
    def _is_ajax_request() -> bool:
        return (
            request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"
            or "application/json" in request.headers.get("Accept", "").lower()
        )

    @bp.route("/agua", methods=["GET", "POST"])
    @login_required
    @permission_required("agua")
    def agua():
        now_for_defaults = now_local()
        fecha = (request.values.get("fecha") or now_for_defaults.strftime("%Y-%m-%d")).strip()
        turno_sugerido = compute_turno_from_hour(now_for_defaults.strftime("%H:%M"))
        lote_sugerido = next_agua_lote(fecha)
        operador_sugerido = default_operador_for_salmuera()
        if request.method == "POST":
            if request.form.get("form_action") == "columnas_estado":
                try:
                    save_columna_intercambio_from_form()
                    db.session.commit()
                    flash("Estado de columna guardado.", "success")
                    return redirect_agua_columnas_anchor(fecha)
                except Exception as e:
                    db.session.rollback()
                    flash(str(e), "danger")
            else:
                try:
                    now = now_local()
                    turno_auto = compute_turno_from_hour(now.strftime("%H:%M"))
                    operador_auto = default_operador_for_salmuera()
                    lote_auto = next_agua_lote(fecha)
                    db.session.add(
                        AguaRegistro(
                            fecha_iso=fecha,
                            hora_hm=now.strftime("%H:%M"),
                            turno=turno_auto,
                            operador=operador_auto,
                            lote=lote_auto,
                            numero_columna=int(request.form.get("numero_columna") or 1),
                            temperatura=float((request.form.get("temperatura") or "0").replace(",", ".")),
                            dureza=float((request.form.get("dureza") or "0").replace(",", ".")),
                            observaciones=(request.form.get("observaciones") or "").strip(),
                            created_at_iso=now.isoformat(timespec="seconds"),
                        )
                    )
                    db.session.commit()
                    if _is_ajax_request():
                        return jsonify({"ok": True, "message": "Registro de agua guardado."}), 200
                    flash("Registro de agua guardado.", "success")
                    return redirect(url_for("produccion.agua", fecha=fecha))
                except Exception as e:
                    db.session.rollback()
                    if _is_ajax_request():
                        return jsonify({"ok": False, "error": str(e)}), 400
                    flash(str(e), "danger")

        rows = db.session.scalars(
            select(AguaRegistro).where(AguaRegistro.fecha_iso == fecha).order_by(AguaRegistro.id)
        ).all()
        columnas_latest = columnas_latest_dict()
        analysis_ref_rows_agua = analysis_ref_ui_rows(AGUA_ANALYSIS_REF_SPECS)
        analysis_ref_map_agua = {r["doc_key"]: r for r in analysis_ref_rows_agua}
        return render_template(
            "produccion/agua.html",
            fecha=fecha,
            registros=[agua_row_to_dict(r) for r in rows],
            module_title=MODULE_LABELS["agua"],
            columnas_latest=columnas_latest,
            columnas_semaforo=columnas_semaforo_global(columnas_latest),
            server_now_iso=now_local().isoformat(timespec="seconds"),
            last_created_at_iso=last_agua_created_at_iso_for_date(fecha),
            analysis_interval_seconds=int(AGUA_ANALYSIS_INTERVAL_SECONDS),
            lote_sugerido=lote_sugerido,
            operador_sugerido=operador_sugerido,
            operador_display_line=operador_display_line(),
            username=current_user().username if current_user() else "",
            turno_sugerido=turno_sugerido,
            columnas_reg_fecha=now_for_defaults.strftime("%d/%m/%Y"),
            columnas_reg_hora=now_for_defaults.strftime("%H:%M"),
            analysis_ref_rows_agua=analysis_ref_rows_agua,
            analysis_ref_map_agua=analysis_ref_map_agua,
        )

    @bp.get("/agua/historial")
    @login_required
    @permission_required("agua")
    def agua_historial():
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()

        q = select(AguaRegistro)
        if desde:
            q = q.where(AguaRegistro.fecha_iso >= desde)
        if hasta:
            q = q.where(AguaRegistro.fecha_iso <= hasta)
        if desde and hasta and desde > hasta:
            flash("Rango de fechas inválido: 'desde' no puede ser mayor que 'hasta'.", "warning")
            q = select(AguaRegistro).where(
                AguaRegistro.fecha_iso >= hasta,
                AguaRegistro.fecha_iso <= desde,
            )
            desde, hasta = hasta, desde

        rows = db.session.scalars(
            q.order_by(
                AguaRegistro.fecha_iso.desc(),
                AguaRegistro.created_at_iso.desc(),
                AguaRegistro.id.desc(),
            ).limit(1000)
        ).all()
        return render_template(
            "produccion/agua_historial.html",
            desde=desde,
            hasta=hasta,
            registros=[agua_row_to_dict(r) for r in rows],
            module_title=MODULE_LABELS["agua"],
        )

    @bp.route("/columnas", methods=["GET", "POST"])
    @login_required
    @permission_required("agua")
    def columnas():
        if request.method == "POST":
            try:
                save_columna_intercambio_from_form()
                db.session.commit()
                flash("Estado de columna guardado.", "success")
            except Exception as e:
                db.session.rollback()
                flash(str(e), "danger")
            fecha = (request.values.get("fecha") or now_local().strftime("%Y-%m-%d")).strip()
            return redirect_agua_columnas_anchor(fecha)
        f_arg = request.args.get("fecha")
        if f_arg:
            return redirect(url_for("produccion.agua", fecha=f_arg) + "#columnas")
        return redirect(url_for("produccion.agua") + "#columnas")
