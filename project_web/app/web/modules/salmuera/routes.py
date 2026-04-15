"""Circuito de salmuera: rutas montadas en el blueprint `produccion`."""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from app.auth_utils import current_user, login_required, permission_required
from app.constants import ANALYSIS_INTERVAL_SECONDS, MODULE_LABELS, SALMUERA_PANEL_ELECTROLIZADORES, SECURITY_DELETE_CODE
from app.extensions import db
from app.models import SalmueraRegistro
from app.services.analysis_ref_pdf import HIPO_CONC_PDF_DOC_KEY, SALMUERA_ANALYSIS_REF_SPECS, analysis_ref_ui_rows
from app.services.hipoclorito_warnings import (
    append_hipoclorito_warnings_to_observaciones,
    evaluate_hipoclorito_operational_warnings,
    hipoclorito_operational_warning_rules_for_js,
)
from app.web.modules.produccion.analysis_ref_handlers import handle_analysis_ref_pdf_request
from app.web.modules.produccion.operadores_query import list_operadores_planta
from app.web.modules.produccion.operativa_context import (
    compute_turno_from_hour,
    default_operador_for_salmuera,
    now_local,
    operador_display_line,
)
from app.web.modules.produccion.salmuera_helpers import (
    count_consecutive_single_cell_for_electrolizador,
    last_salmuera_row_dict_for_electrolizador_on_date,
    next_salmuera_lote,
    parse_voltajes,
    salmuera_row_to_dict,
    salmuera_timer_rows_for_date,
)


def register_salmuera_routes(bp: Blueprint) -> None:
    def _is_ajax_request() -> bool:
        return (
            request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"
            or "application/json" in request.headers.get("Accept", "").lower()
        )

    @bp.route("/salmuera/hipo-conc-pdf", methods=["GET", "POST"])
    @login_required
    @permission_required("salmuera")
    def salmuera_hipo_conc_pdf():
        """Compatibilidad: URL histórica del PDF de Hipo conc."""
        return handle_analysis_ref_pdf_request(HIPO_CONC_PDF_DOC_KEY)

    @bp.route("/salmuera", methods=["GET", "POST"])
    @login_required
    @permission_required("salmuera")
    def salmuera():
        now_for_defaults = now_local()
        fecha = (request.values.get("fecha") or now_for_defaults.strftime("%Y-%m-%d")).strip()
        turno_sugerido = compute_turno_from_hour(now_for_defaults.strftime("%H:%M"))
        lote_sugerido = next_salmuera_lote(fecha)
        operador_sugerido = default_operador_for_salmuera()
        if request.method == "POST" and request.form.get("action") == "guardar":
            try:
                n = int((request.form.get("cantidad_celdas") or "0").strip())
                if n < 1:
                    raise ValueError("Cantidad de celdas inválida.")
                if n > 20:
                    raise ValueError("La cantidad de celdas no puede superar 20.")
                electrolizador = int((request.form.get("electrolizador") or "0").strip())
                if electrolizador <= 0:
                    raise ValueError("El electrolizador debe ser un número mayor a 0.")
                if n == 1:
                    consec = count_consecutive_single_cell_for_electrolizador(electrolizador)
                    if consec >= 2:
                        raise ValueError(
                            "Para este electrolizador ya hay 2 cargas seguidas con 1 celda. "
                            "La siguiente carga debe tener cantidad de celdas mayor a 1."
                        )
                volts_text = (request.form.get("voltajes") or "").strip()
                if not volts_text:
                    raw_parts: list[str] = []
                    for i in range(1, n + 1):
                        raw_parts.append((request.form.get(f"voltaje_{i}") or "").strip())
                    volts_text = ",".join(raw_parts)
                volts = parse_voltajes(volts_text, n)
                if n == 1:
                    v = float(volts[0])
                    if v <= 0:
                        raise ValueError("Con 1 celda, el voltaje debe ser un número mayor a 0.")
                else:
                    for i, v in enumerate(volts, start=1):
                        if v < 2.5 or v > 4.5:
                            raise ValueError(
                                f"Voltaje {i} fuera de rango. Con más de 1 celda, cada voltaje debe estar entre 2.5 y 4.5."
                            )
                now = now_local()
                turno_auto = compute_turno_from_hour(now.strftime("%H:%M"))
                caudal_agua = float((request.form.get("caudal_agua_l_h") or "0").replace(",", "."))
                caudal_salmuera = float((request.form.get("caudal_salmuera_l_h") or "0").replace(",", "."))
                if caudal_agua >= caudal_salmuera:
                    raise ValueError("El caudal de agua debe ser menor que el caudal de salmuera.")
                operador_auto = default_operador_for_salmuera()
                lote_auto = next_salmuera_lote(fecha)
                hipo_exceso_soda = float((request.form.get("hipo_exceso_soda") or "0").replace(",", "."))
                sal_conc = float((request.form.get("sal_conc") or "0").replace(",", "."))
                sal_ph = float((request.form.get("sal_ph") or "0").replace(",", "."))
                declor_ph = float((request.form.get("declor_ph") or "0").replace(",", "."))
                obs_raw = (request.form.get("observaciones") or "").strip()
                op_warnings = evaluate_hipoclorito_operational_warnings(
                    hipo_exceso_soda=hipo_exceso_soda,
                    sal_conc=sal_conc,
                    sal_ph=sal_ph,
                    declor_ph=declor_ph,
                )
                observaciones_final = append_hipoclorito_warnings_to_observaciones(obs_raw, op_warnings)
                data = SalmueraRegistro(
                    fecha_iso=fecha,
                    hora_hm=now.strftime("%H:%M"),
                    electrolizador=electrolizador,
                    cantidad_celdas=n,
                    turno=turno_auto,
                    voltajes_json=json.dumps(volts, ensure_ascii=False),
                    voltaje_total=float(sum(volts)),
                    amperaje=float((request.form.get("amperaje") or "0").replace(",", ".")),
                    caudal_agua_l_h=caudal_agua,
                    caudal_salmuera_l_h=caudal_salmuera,
                    hipo_conc=float((request.form.get("hipo_conc") or "0").replace(",", ".")),
                    hipo_exceso_soda=hipo_exceso_soda,
                    sal_temp=float((request.form.get("sal_temp") or "0").replace(",", ".")),
                    sal_conc=sal_conc,
                    sal_ph=sal_ph,
                    soda_conc=float((request.form.get("soda_conc") or "0").replace(",", ".")),
                    declor_ph=declor_ph,
                    operador=operador_auto,
                    lote=lote_auto,
                    observaciones=observaciones_final,
                    atraso_motivo=(request.form.get("atraso_motivo") or "").strip(),
                    created_at_iso=now.isoformat(timespec="seconds"),
                )
                db.session.add(data)
                db.session.commit()
                registro_dict = salmuera_row_to_dict(data)
                ultimo_panel = last_salmuera_row_dict_for_electrolizador_on_date(fecha, electrolizador)
                timer_rows = salmuera_timer_rows_for_date(fecha)
                panel_timer = next(
                    (row for row in timer_rows if int(row.get("electrolizador", 0)) == int(electrolizador)),
                    {"electrolizador": electrolizador, "last_created_at_iso": data.created_at_iso},
                )
                if _is_ajax_request():
                    return (
                        jsonify(
                            {
                                "ok": True,
                                "message": "Registro de salmuera guardado.",
                                "saved_electrolizador": int(electrolizador),
                                "registro": registro_dict,
                                "ultimo": ultimo_panel,
                                "timer_row": panel_timer,
                            }
                        ),
                        200,
                    )
                flash("Registro de salmuera guardado.", "success")
                return redirect(url_for("produccion.salmuera", fecha=fecha))
            except Exception as e:
                db.session.rollback()
                if _is_ajax_request():
                    return jsonify({"ok": False, "error": str(e)}), 400
                flash(str(e), "danger")

        if request.method == "POST" and request.form.get("action") == "borrar":
            fecha_del = (request.form.get("fecha") or fecha).strip()
            rid = int((request.form.get("reg_id") or 0))
            codigo = (request.form.get("codigo_seguridad") or "").strip()
            if codigo != SECURITY_DELETE_CODE:
                flash("Código de seguridad incorrecto.", "danger")
            else:
                row = db.session.get(SalmueraRegistro, rid)
                if row:
                    db.session.delete(row)
                    db.session.commit()
                    flash("Registro eliminado.", "info")
            return redirect(url_for("produccion.salmuera", fecha=fecha_del))

        rows = db.session.scalars(
            select(SalmueraRegistro)
            .where(SalmueraRegistro.fecha_iso == fecha)
            .order_by(SalmueraRegistro.created_at_iso.desc(), SalmueraRegistro.id.desc())
        ).all()
        registros: list[dict[str, Any]] = [salmuera_row_to_dict(r) for r in rows]

        analysis_ref_rows_salmuera = analysis_ref_ui_rows(SALMUERA_ANALYSIS_REF_SPECS)
        analysis_ref_map_salmuera = {r["doc_key"]: r for r in analysis_ref_rows_salmuera}

        salmuera_ultimo_por_electrolizador: dict[int, dict[str, Any] | None] = {
            int(eid): last_salmuera_row_dict_for_electrolizador_on_date(fecha, int(eid))
            for eid in SALMUERA_PANEL_ELECTROLIZADORES
        }

        return render_template(
            "produccion/salmuera.html",
            fecha=fecha,
            registros=registros,
            operadores=list_operadores_planta(),
            lote_sugerido=lote_sugerido,
            operador_sugerido=operador_sugerido,
            operador_display_line=operador_display_line(),
            module_title=MODULE_LABELS["salmuera"],
            username=current_user().username if current_user() else "",
            turno_sugerido=turno_sugerido,
            server_now_iso=now_local().isoformat(timespec="seconds"),
            salmuera_timer_rows=salmuera_timer_rows_for_date(fecha),
            salmuera_panel_electrolizadores=list(SALMUERA_PANEL_ELECTROLIZADORES),
            salmuera_ultimo_por_electrolizador=salmuera_ultimo_por_electrolizador,
            analysis_interval_seconds=int(ANALYSIS_INTERVAL_SECONDS),
            analysis_ref_rows_salmuera=analysis_ref_rows_salmuera,
            analysis_ref_map_salmuera=analysis_ref_map_salmuera,
            hipoclorito_warning_rules=hipoclorito_operational_warning_rules_for_js(),
        )

    @bp.get("/salmuera/historial")
    @login_required
    @permission_required("salmuera")
    def salmuera_historial():
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()

        q = select(SalmueraRegistro)
        if desde:
            q = q.where(SalmueraRegistro.fecha_iso >= desde)
        if hasta:
            q = q.where(SalmueraRegistro.fecha_iso <= hasta)
        if desde and hasta and desde > hasta:
            flash("Rango de fechas inválido: 'desde' no puede ser mayor que 'hasta'.", "warning")
            q = select(SalmueraRegistro).where(
                SalmueraRegistro.fecha_iso >= hasta,
                SalmueraRegistro.fecha_iso <= desde,
            )
            desde, hasta = hasta, desde

        rows = db.session.scalars(
            q.order_by(
                SalmueraRegistro.fecha_iso.desc(),
                SalmueraRegistro.created_at_iso.desc(),
                SalmueraRegistro.id.desc(),
            ).limit(1000)
        ).all()
        registros: list[dict[str, Any]] = [salmuera_row_to_dict(r) for r in rows]
        return render_template(
            "produccion/salmuera_historial.html",
            desde=desde,
            hasta=hasta,
            registros=registros,
            module_title=MODULE_LABELS["salmuera"],
        )
