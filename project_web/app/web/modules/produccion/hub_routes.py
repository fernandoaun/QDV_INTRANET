"""Hub de producción, alta de operadores y documentos de análisis por doc_key."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth_utils import (
    current_user,
    login_required,
    permission_required,
    user_can_access_production_hub,
)
from app.services import produccion_hub_service
from app.services.analysis_ref_pdf import analysis_ref_pdf_doc_keys
from app.web.modules.produccion.analysis_ref_handlers import handle_analysis_ref_pdf_request


def register_produccion_hub_routes(bp: Blueprint) -> None:
    @bp.get("/")
    @login_required
    def hub():
        u = current_user()
        if not user_can_access_production_hub(u):
            flash("No tenés permiso para acceder a Producción.", "warning")
            return redirect(url_for("main.dashboard"))
        return render_template("produccion/hub.html")

    @bp.post("/operadores/agregar")
    @login_required
    @permission_required("produccion")
    def operador_agregar():
        nombre = (request.form.get("nombre") or "").strip()
        if nombre:
            try:
                saved = produccion_hub_service.add_operador(nombre)
                flash(f"Operador {saved!r} agregado.", "success")
            except Exception as e:
                flash(str(e), "danger")
        return redirect(request.referrer or url_for("produccion.hub"))

    @bp.route("/documentos/analisis-ref/<doc_key>", methods=["GET", "POST"])
    @login_required
    def analysis_ref_pdf(doc_key: str):
        if doc_key not in analysis_ref_pdf_doc_keys():
            abort(404)
        return handle_analysis_ref_pdf_request(doc_key)
