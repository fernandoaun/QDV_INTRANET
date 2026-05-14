"""Circuito reactor: rutas en el blueprint `produccion`."""

from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, url_for
from sqlalchemy import select

from app.auth_utils import current_user, login_required, permission_required
from app.constants import ANALYSIS_INTERVAL_SECONDS, MODULE_LABELS
from app.extensions import db
from app.models import ReactorRegistro, SalmueraAnalisis8hs
from app.services import salmuera_analisis_8hs_service as analisis8_svc
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
    parse_required_float,
    reactor_row_to_dict,
)


def register_reactor_routes(bp: Blueprint) -> None:
    def _is_ajax_request() -> bool:
        return (
            request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"
            or "application/json" in request.headers.get("Accept", "").lower()
        )

    @bp.route("/reactor", methods=["GET", "POST"])
    @login_required
    @permission_required("reactor")
    def reactor():
        now_for_defaults = now_local()
        fecha = (request.values.get("fecha") or now_for_defaults.strftime("%Y-%m-%d")).strip()
        turno_sugerido = compute_turno_from_hour(now_for_defaults.strftime("%H:%M"))
        operador_sugerido = default_operador_for_salmuera()
        if request.method == "POST" and request.form.get("action") == "guardar_analisis_8hs":
            try:
                now = now_local()
                row = analisis8_svc.create_from_form(
                    request.form,
                    now=now,
                    operador=operador_display_line() or default_operador_for_salmuera(),
                )
                db.session.commit()
                status = analisis8_svc.build_status(now_local())
                if _is_ajax_request():
                    return (
                        jsonify(
                            {
                                "ok": True,
                                "message": "Análisis 8 hs de salmuera guardado.",
                                "registro": analisis8_svc.row_to_dict(row),
                                "status": status,
                            }
                        ),
                        200,
                    )
                flash("Análisis 8 hs de salmuera guardado.", "success")
                return redirect(url_for("produccion.reactor", fecha=fecha))
            except Exception as e:
                db.session.rollback()
                if _is_ajax_request():
                    return jsonify({"ok": False, "error": str(e)}), 400
                flash(str(e), "danger")

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
                orp = parse_required_float(request.form.get("orp"), "ORP (mV)")
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
                        orp=orp,
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
            analisis8_status=analisis8_svc.build_status(now_local()),
            analisis8_interval_seconds=analisis8_svc.ANALISIS_8HS_INTERVAL_SECONDS,
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

    @bp.get("/reactor/analisis-8hs/historial")
    @login_required
    @permission_required("reactor")
    def salmuera_analisis_8hs_historial():
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()
        if desde and hasta and desde > hasta:
            flash("Rango de fechas inválido: 'desde' no puede ser mayor que 'hasta'.", "warning")
            desde, hasta = hasta, desde
        rows = analisis8_svc.filtered_rows(desde, hasta)
        return render_template(
            "produccion/salmuera_analisis_8hs_historial.html",
            desde=desde,
            hasta=hasta,
            registros=[analisis8_svc.row_to_dict(r) for r in rows],
            module_title=MODULE_LABELS["reactor"],
            history_file_endpoint="produccion.salmuera_analisis_8hs_archivo_reactor",
        )

    @bp.get("/reactor/analisis-8hs/export.xlsx")
    @login_required
    @permission_required("reactor")
    def salmuera_analisis_8hs_export_xlsx():
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()
        if desde and hasta and desde > hasta:
            desde, hasta = hasta, desde
        buf = analisis8_svc.export_excel(desde, hasta)
        fname = f"salmuera_analisis_8hs_{now_local().date().isoformat()}.xlsx"
        return send_file(
            buf,
            as_attachment=True,
            download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @bp.route("/reactor/analisis-8hs/<int:registro_id>/archivo/<field>", methods=["GET", "POST"])
    @login_required
    @permission_required("reactor")
    def salmuera_analisis_8hs_archivo_reactor(registro_id: int, field: str):
        if field not in analisis8_svc.ATTACHMENT_FIELDS:
            return ("", 404)
        row = db.session.get(SalmueraAnalisis8hs, registro_id)
        if row is None:
            return ("", 404)
        meta = analisis8_svc.ATTACHMENT_FIELDS[field]
        if request.method == "GET":
            resolved = analisis8_svc.attachment_resolve_path(row, field)
            if resolved is None:
                return ("", 404)
            suffix = resolved.suffix.lower()
            mimetype = "application/pdf" if suffix == ".pdf" else None
            return send_file(resolved, mimetype=mimetype, as_attachment=False)

        action = (request.form.get("action") or "").strip()
        if action == "delete":
            u = current_user()
            if u is None or not u.is_admin:
                flash("Solo administradores pueden eliminar archivos de análisis.", "danger")
                return redirect(request.referrer or url_for("produccion.salmuera_analisis_8hs_historial"))
            analisis8_svc.delete_attachment(row, field)
            db.session.commit()
            flash(f"Archivo de {meta['label']} eliminado.", "info")
            return redirect(request.referrer or url_for("produccion.salmuera_analisis_8hs_historial"))

        fs = request.files.get("archivo")
        u = current_user()
        if u is None or not u.is_admin:
            flash("Solo administradores pueden subir o reemplazar PDFs de análisis.", "danger")
            return redirect(request.referrer or url_for("produccion.salmuera_analisis_8hs_historial"))
        if fs is None or not fs.filename:
            flash("Seleccioná un archivo PDF.", "warning")
            return redirect(request.referrer or url_for("produccion.salmuera_analisis_8hs_historial"))
        try:
            analisis8_svc.save_attachment(row, field, fs)
            db.session.commit()
            flash(f"Archivo de {meta['label']} guardado.", "success")
        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")
        return redirect(request.referrer or url_for("produccion.salmuera_analisis_8hs_historial"))
