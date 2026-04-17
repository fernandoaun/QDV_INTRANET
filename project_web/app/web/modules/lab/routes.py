"""Reactivos de laboratorio en planta (catálogo, PDF, consumo)."""

from __future__ import annotations

from uuid import uuid4

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy import select

from app.auth_utils import current_user, login_required, permission_required
from app.constants import MODULE_LABELS
from app.extensions import db
from app.models import LaboratoryReagent, LaboratoryReagentUsage
from app.services import shift_handover_service as sh
from app.web.modules.produccion.analysis_ref_handlers import validate_pdf_upload
from app.web.modules.produccion.lab_reagents_helpers import (
    lab_reagent_pdf_is_readable,
    lab_reagent_pdf_resolve_path,
    lab_reagents_storage_dir,
    lab_usage_shift_session_id,
    parse_lab_usage_used_at_iso,
)
from app.web.modules.produccion.operativa_context import now_local


def register_lab_reagents_routes(bp: Blueprint) -> None:
    @bp.route("/lab-reactivos", methods=["GET"])
    @login_required
    @permission_required("lab_reactivos")
    def lab_reactivos():
        reagent_rows = list(
            db.session.scalars(select(LaboratoryReagent).order_by(LaboratoryReagent.name.asc())).all()
        )
        reagent_display = [
            {"id": r.id, "name": r.name, "pdf_ok": lab_reagent_pdf_is_readable(r)} for r in reagent_rows
        ]
        return render_template(
            "produccion/lab_reactivos.html",
            module_title=MODULE_LABELS["lab_reactivos"],
            reagent_display=reagent_display,
        )

    @bp.get("/lab-reactivos/pdf/<int:reagent_id>")
    @login_required
    @permission_required("lab_reactivos")
    def lab_reactivos_pdf(reagent_id: int):
        row = db.session.get(LaboratoryReagent, reagent_id)
        if row is None or not lab_reagent_pdf_is_readable(row):
            abort(404)
        resolved = lab_reagent_pdf_resolve_path(row)
        if resolved is None:
            abort(404)
        return send_file(
            resolved,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=row.pdf_original_filename or f"reactivo-{reagent_id}.pdf",
        )

    @bp.post("/lab-reactivos/nuevo")
    @login_required
    def lab_reactivos_nuevo():
        u = current_user()
        if u is None or not u.is_admin:
            flash("Solo administradores pueden dar de alta reactivos en el catálogo.", "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("El nombre del reactivo es obligatorio.", "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        fs = request.files.get("pdf")
        try:
            orig_name = validate_pdf_upload(fs)
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        stored = f"{uuid4().hex}.pdf"
        dest = lab_reagents_storage_dir() / stored
        now_iso = now_local().isoformat(timespec="seconds")
        row = LaboratoryReagent(
            name=name[:256],
            pdf_stored_filename=stored,
            pdf_original_filename=orig_name,
            created_by_user_id=u.id,
            created_at_iso=now_iso,
            updated_at_iso=now_iso,
        )
        db.session.add(row)
        try:
            fs.save(str(dest))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
            flash(str(e), "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        flash("Reactivo cargado en el catálogo.", "success")
        return redirect(url_for("produccion.lab_reactivos"))

    @bp.post("/lab-reactivos/registrar-consumo")
    @login_required
    @permission_required("lab_reactivos")
    def lab_reactivos_registrar_consumo():
        u = current_user()
        if u is None:
            return redirect(url_for("auth.login"))
        try:
            rid = int((request.form.get("reagent_id") or "0").strip())
        except ValueError:
            flash("Reactivo no válido.", "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        reg = db.session.get(LaboratoryReagent, rid)
        if reg is None:
            flash("Reactivo no válido.", "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        try:
            qty = float((request.form.get("quantity") or "").replace(",", "."))
        except ValueError:
            flash("La cantidad debe ser numérica.", "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        if qty <= 0 or qty != qty:
            flash("La cantidad debe ser mayor a cero.", "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        unit_other = (request.form.get("unit_other") or "").strip()
        unit = (request.form.get("unit") or "").strip()
        if unit == "__otro__":
            unit = unit_other
        unit_clean = unit.strip()[:64]
        if not unit_clean:
            flash("Indicá la unidad (elegí una opción o escribí otra).", "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        try:
            used_iso = parse_lab_usage_used_at_iso(request.form.get("used_at") or "")
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        notes = (request.form.get("notes") or "").strip() or None
        open_s = sh.get_open_shift_session()
        op_line = (sh.operador_turno_display_line(u, open_s) or "").strip() or (u.username or "").strip()
        now_iso = now_local().isoformat(timespec="seconds")
        usage = LaboratoryReagentUsage(
            reagent_id=reg.id,
            quantity=qty,
            unit=unit_clean,
            used_at_iso=used_iso,
            registered_by_user_id=u.id,
            operator_display_name=op_line[:512],
            shift_session_id=lab_usage_shift_session_id(),
            notes=notes,
            created_at_iso=now_iso,
            updated_at_iso=now_iso,
        )
        db.session.add(usage)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")
            return redirect(url_for("produccion.lab_reactivos"))
        flash("Consumo de laboratorio registrado.", "success")
        return redirect(url_for("produccion.lab_reactivos"))
