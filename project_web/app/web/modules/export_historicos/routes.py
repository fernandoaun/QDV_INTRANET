from __future__ import annotations

from datetime import timedelta

from flask import current_app, flash, redirect, render_template, request, send_file, url_for

from app.auth_utils import current_user, login_required
from app.security_http import request_path_for_login_next
from app.services.historicos_export_service import (
    MAX_ROWS_PER_SHEET,
    allowed_export_keys_for_user,
    build_historicos_workbook,
    export_download_filename,
    export_module_definitions,
    parse_and_validate_rango_fechas,
)
from app.utils.datetime_operacion import now_operacion_naive_local

from . import bp


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    u = current_user()
    if u is None:
        return redirect(url_for("auth.login", next=request_path_for_login_next()))

    allowed = allowed_export_keys_for_user(u)
    if not allowed:
        flash("No tenés permisos para exportar históricos de ningún módulo.", "warning")
        return redirect(url_for("main.dashboard"))

    module_rows = [
        {"key": m.key, "label": m.label}
        for m in export_module_definitions()
        if m.key in allowed
    ]

    if request.method == "POST":
        ok, err, d0, d1 = parse_and_validate_rango_fechas(
            request.form.get("fecha_desde") or "",
            request.form.get("fecha_hasta") or "",
        )
        if not ok or d0 is None or d1 is None:
            flash(err or "Rango de fechas inválido.", "danger")
            return redirect(url_for("export_historicos.index"))

        selected = [k for k in request.form.getlist("modulos") if k in allowed]
        if not selected:
            flash("Seleccioná al menos un módulo para exportar.", "warning")
            return redirect(url_for("export_historicos.index"))

        try:
            bio, gen_err = build_historicos_workbook(selected, d0, d1)
        except Exception:
            current_app.logger.exception("Fallo al generar exportación de históricos Excel")
            flash(
                "Ocurrió un error al generar el archivo. Si acabás de desplegar, comprobá que el build "
                "instaló las dependencias (openpyxl). Si persiste, contactá soporte.",
                "danger",
            )
            return redirect(url_for("export_historicos.index"))
        if gen_err or bio is None:
            flash(gen_err or "No se pudo generar el archivo.", "warning")
            return redirect(url_for("export_historicos.index"))

        fname = export_download_filename(d0, d1)
        return send_file(
            bio,
            as_attachment=True,
            download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    today = now_operacion_naive_local().date()
    return render_template(
        "export/historicos.html",
        module_rows=module_rows,
        default_desde=(today - timedelta(days=30)).isoformat(),
        default_hasta=today.isoformat(),
        max_rows_per_sheet=MAX_ROWS_PER_SHEET,
    )
