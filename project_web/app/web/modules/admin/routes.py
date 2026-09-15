from __future__ import annotations

import re

from urllib.parse import urlencode

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from app.auth_utils import (
    admin_required,
    current_user,
    login_required,
    set_session_for_user,
    user_can_view_admin_configuration,
)
from app.constants import PERMISSION_LABELS, PERMISSION_TREE
from app.extensions import db
from app.models import Equipo, PermisoUsuario, User
from app.services import permiso_asignacion_service as perm_asig
from app.security_http import json_preview, truncate_plain_text
from app.services import security_audit_service as audit_svc
from app.services.deadline_alert_email_service import (
    add_email,
    delete_email_row,
    list_emails_ordered,
    merged_recipient_addresses,
    normalize_validate_email,
)
from app.services import plant_stop_service as plant_stop_svc
from app.services import personal_service as personal_svc
from app.services import stock_alert_email_service as stock_alert_svc
from app.services import sgi_anexo_service as anexo_svc
from app.services.mail_service import enviar_mail, is_mail_fully_configured, smtp_diagnostic_summary
from app.services.personal_epp_reminder_service import run_entrega_epp_reminders
from app.services.vencimiento_reminder_service import run_vencimiento_reminders
from app.utils.datetime_operacion import now_operacion_local_iso_seconds
from app.user_roles import (
    ROLE_ADMINISTRADOR,
    ROLE_LABELS,
    USER_ROLES_ORDERED,
    role_template_perm_sets,
    validate_rol_submitted,
)

bp = Blueprint("admin_users", __name__, url_prefix="/admin")


@bp.get("/usuarios")
@login_required
def list_users():
    u = current_user()
    if u is None or not user_can_view_admin_configuration(u):
        flash("No tenés permiso para acceder a usuarios.", "warning")
        return redirect(url_for("main.dashboard"))
    rows = db.session.scalars(select(User).order_by(User.username)).all()
    personal_svc.sync_empleados_from_users()
    return render_template(
        "admin/users_list.html",
        users=rows,
        legajo_status=personal_svc.legajo_status_by_user_id(sync_users=False),
        user_requires_legajo=personal_svc.user_requires_legajo,
        viewer_may_manage_users=bool(u.is_admin),
        organigrama_puestos=anexo_svc.organigrama_puesto_opciones(),
        permisos_recursos_nuevos=perm_asig.new_unassigned_resources(),
    )


def _refresh_session_if_self(user: User) -> None:
    viewer = current_user()
    if viewer is None or int(viewer.id) != int(user.id):
        return
    set_session_for_user(user)


def _perfiles_puestos_context(puesto_id: str | None = None) -> dict:
    puestos = anexo_svc.organigrama_puesto_opciones()
    counts = perm_asig.puesto_assigned_counts()
    selected = (puesto_id or request.args.get("puesto") or "").strip()
    if not selected:
        selected = perm_asig.PUESTO_COMUN_ID
    valid = {str(p["id"]) for p in puestos}
    valid.add(perm_asig.PUESTO_COMUN_ID)
    if selected not in valid:
        selected = perm_asig.PUESTO_COMUN_ID
    is_comun = perm_asig.is_puesto_comun(selected)
    comun_v, comun_e = perm_asig.comunes_perm_sets()
    if is_comun:
        view_set, edit_set = comun_v, comun_e
        lock_comun = False
    else:
        view_set, edit_set = perm_asig.puesto_perm_sets(selected)
        lock_comun = True
    selected_titulo = "Comunes a todos"
    if not is_comun:
        selected_titulo = next((p["titulo"] for p in puestos if p["id"] == selected), selected)
    sel = [str(x).strip() for x in request.args.getlist("sel") if str(x).strip() in valid]
    return {
        "organigrama_puestos": puestos,
        "puesto_selected": selected,
        "puesto_selected_titulo": selected_titulo,
        "puesto_is_comun": is_comun,
        "puesto_perm_counts": counts,
        "puesto_sel": sel,
        "perms_set": view_set,
        "perms_edit_set": edit_set,
        "comun_view_set": comun_v,
        "comun_edit_set": comun_e,
        "lock_comun": lock_comun,
        "permission_tree": PERMISSION_TREE,
        "permission_labels": PERMISSION_LABELS,
        "permisos_recursos_nuevos": perm_asig.new_unassigned_resources(),
    }


@bp.get("/perfiles")
@login_required
def perfiles_recursos():
    u = current_user()
    if u is None or not user_can_view_admin_configuration(u):
        flash("No tenés permiso para acceder a perfiles.", "warning")
        return redirect(url_for("main.dashboard"))
    ambito = (request.args.get("ambito") or "puesto").strip().lower()
    if ambito not in ("puesto", "persona"):
        ambito = "puesto"
    viewer_may_mutate = bool(u.is_admin)
    persona_user = None
    persona_ctx: dict = {}
    if ambito == "persona":
        uid_raw = request.args.get("user_id") or ""
        try:
            uid = int(uid_raw)
        except (TypeError, ValueError):
            uid = 0
        users = db.session.scalars(select(User).order_by(User.username)).all()
        if uid:
            persona_user = db.session.get(User, uid)
        if persona_user is None and users:
            persona_user = next((x for x in users if not perm_asig.user_uses_fixed_perm_template(x)), None)
        if persona_user is not None:
            puesto_ids = anexo_svc.organigrama_node_ids_for_user(int(persona_user.id))
            pv, pe = perm_asig.view_edit_for_puestos(puesto_ids)
            cv, ce = perm_asig.comunes_perm_sets()
            rv, re = role_template_perm_sets(persona_user.rol)
            view_l, edit_l = perm_asig.effective_perm_lists_for_user(persona_user)
            persona_ctx = {
                "hide_perm_grid": perm_asig.user_uses_fixed_perm_template(persona_user),
                "perms_set": set(view_l),
                "perms_edit_set": set(edit_l),
                "role_view_set": rv,
                "role_edit_set": re,
                "puesto_view_set": pv,
                "puesto_edit_set": pe,
                "comun_view_set": cv,
                "comun_edit_set": ce,
                "organigrama_puestos_selected": puesto_ids,
            }
        persona_ctx["users"] = users
        persona_ctx["persona_user"] = persona_user
        persona_ctx["persona_sel"] = []
        for raw in request.args.getlist("sel"):
            try:
                persona_ctx["persona_sel"].append(int(raw))
            except (TypeError, ValueError):
                continue
        return render_template(
            "admin/perfiles.html",
            ambito="persona",
            viewer_may_mutate=viewer_may_mutate,
            permission_tree=PERMISSION_TREE,
            permission_labels=PERMISSION_LABELS,
            permisos_recursos_nuevos=perm_asig.new_unassigned_resources(),
            organigrama_puestos=anexo_svc.organigrama_puesto_opciones(),
            **persona_ctx,
        )
    ctx = _perfiles_puestos_context()
    return render_template(
        "admin/perfiles.html",
        ambito="puesto",
        viewer_may_mutate=viewer_may_mutate,
        **ctx,
    )


@bp.post("/perfiles/puesto")
@login_required
@admin_required
def perfiles_guardar_puesto():
    puesto_id = (request.form.get("puesto_id") or "").strip()
    valid = {p["id"] for p in anexo_svc.organigrama_puesto_opciones()}
    valid.add(perm_asig.PUESTO_COMUN_ID)
    if not puesto_id or puesto_id not in valid:
        flash("Seleccioná un puesto válido del organigrama.", "danger")
        return redirect(url_for("admin_users.perfiles_recursos", ambito="puesto"))
    flags = perm_asig.perm_flags_from_form(request.form)
    perm_asig.replace_puesto_permissions(puesto_id, flags)
    db.session.commit()
    viewer = current_user()
    if viewer is not None and not viewer.is_admin:
        _refresh_session_if_self(viewer)
    elif viewer is not None:
        mine = set(anexo_svc.organigrama_node_ids_for_user(int(viewer.id)))
        if puesto_id in mine or perm_asig.is_puesto_comun(puesto_id):
            _refresh_session_if_self(viewer)
    audit_svc.record_event(
        action="puesto_permissions_update",
        module="admin",
        actor=current_user(),
        entity_type="puesto",
        entity_id=None,
        detail=truncate_plain_text(puesto_id, max_len=220),
        new_value=json_preview(
            {k: {"ver": fv, "editar": fe} for k, (fv, fe) in flags.items() if fv}
        ),
    )
    if perm_asig.is_puesto_comun(puesto_id):
        flash(
            "Recursos comunes guardados: aplican a todos los puestos. Quienes ya estaban logueados tienen que volver a entrar.",
            "success",
        )
    else:
        flash(
            "Recursos extra de este puesto guardados. Quienes ya estaban logueados tienen que volver a entrar para ver el cambio.",
            "success",
        )
    return redirect(url_for("admin_users.perfiles_recursos", ambito="puesto", puesto=puesto_id))


@bp.post("/perfiles/puestos/sumar")
@login_required
@admin_required
def perfiles_sumar_puestos():
    valid = {p["id"] for p in anexo_svc.organigrama_puesto_opciones()}
    valid.add(perm_asig.PUESTO_COMUN_ID)
    ids = [str(x).strip() for x in request.form.getlist("puesto_ids") if str(x).strip() in valid]
    if not ids:
        flash("Tildá uno o más puestos (o Comunes a todos) para sumarles permisos.", "warning")
        return redirect(url_for("admin_users.perfiles_recursos", ambito="puesto"))
    flags = perm_asig.perm_flags_from_form(request.form)
    if not any(fv for fv, _fe in flags.values()):
        flash("Tildá al menos un recurso en la grilla para sumárselo a los seleccionados.", "warning")
        return redirect(url_for("admin_users.perfiles_recursos", ambito="puesto", puesto=request.form.get("puesto_id")))
    changed = 0
    for pid in ids:
        if perm_asig.grant_puesto_permissions(pid, flags):
            changed += 1
    db.session.commit()
    audit_svc.record_event(
        action="puesto_permissions_grant_bulk",
        module="admin",
        actor=current_user(),
        entity_type="puesto",
        detail=truncate_plain_text(",".join(ids), max_len=220),
        new_value=json_preview({k: {"ver": fv, "editar": fe} for k, (fv, fe) in flags.items() if fv}),
    )
    flash(
        f"Se sumaron los recursos tildados a {changed} de {len(ids)} destino(s). Quienes ya estaban logueados tienen que volver a entrar.",
        "success",
    )
    focus = (request.form.get("puesto_id") or perm_asig.PUESTO_COMUN_ID).strip()
    url = url_for("admin_users.perfiles_recursos", ambito="puesto", puesto=focus)
    if ids:
        url += "&" + urlencode([("sel", s) for s in ids])
    return redirect(url)


@bp.post("/perfiles/personas/sumar")
@login_required
@admin_required
def perfiles_sumar_personas():
    raw_ids = request.form.getlist("user_ids")
    uids: list[int] = []
    for raw in raw_ids:
        try:
            uids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not uids:
        flash("Tildá una o más personas para sumarles permisos.", "warning")
        return redirect(url_for("admin_users.perfiles_recursos", ambito="persona"))
    flags = perm_asig.perm_flags_from_form(request.form)
    if not any(fv for fv, _fe in flags.values()):
        flash("Tildá al menos un recurso en la grilla para sumárselo a las seleccionadas.", "warning")
        return redirect(url_for("admin_users.perfiles_recursos", ambito="persona"))
    changed = 0
    skipped = 0
    last_ok: int | None = None
    for uid in uids:
        u = db.session.get(User, uid)
        if u is None:
            continue
        if perm_asig.user_uses_fixed_perm_template(u):
            skipped += 1
            continue
        if perm_asig.grant_user_permissions(u, flags):
            changed += 1
            last_ok = int(u.id)
            _refresh_session_if_self(u)
    db.session.commit()
    audit_svc.record_event(
        action="user_permissions_grant_bulk",
        module="admin",
        actor=current_user(),
        entity_type="user",
        detail=truncate_plain_text(",".join(str(i) for i in uids), max_len=220),
        new_value=json_preview({k: {"ver": fv, "editar": fe} for k, (fv, fe) in flags.items() if fv}),
    )
    msg = f"Se sumaron los recursos tildados a {changed} persona(s)."
    if skipped:
        msg += f" Se omitieron {skipped} con plantilla fija (administrador, Angel, SGC o laboratorista)."
    flash(msg, "success" if changed else "info")
    focus = last_ok or (int(request.form.get("user_id") or 0) or None)
    url = url_for("admin_users.perfiles_recursos", ambito="persona", **({"user_id": focus} if focus else {}))
    if uids:
        url += "&" + urlencode([("sel", str(i)) for i in uids])
    return redirect(url)


@bp.post("/perfiles/persona/<int:uid>")
@login_required
@admin_required
def perfiles_guardar_persona(uid: int):
    u = db.session.get(User, uid)
    if u is None:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("admin_users.perfiles_recursos", ambito="persona"))
    if perm_asig.user_uses_fixed_perm_template(u):
        flash("Este perfil usa una plantilla fija; no se asignan recursos por persona.", "warning")
        return redirect(url_for("admin_users.perfiles_recursos", ambito="persona", user_id=uid))
    puesto_ids = anexo_svc.organigrama_node_ids_for_user(int(u.id))
    base_v, base_e = perm_asig.base_perm_sets_for_role_and_puestos(u.rol, puesto_ids)
    flags = perm_asig.perm_flags_from_form(request.form)
    perm_asig.replace_user_permission_overrides(u, flags, base_v, base_e)
    db.session.commit()
    _refresh_session_if_self(u)
    audit_svc.record_event(
        action="user_permissions_update",
        module="admin",
        actor=current_user(),
        entity_type="user",
        entity_id=int(u.id),
        detail=truncate_plain_text(u.username, max_len=220),
    )
    flash("Recursos de la persona guardados.", "success")
    return redirect(url_for("admin_users.perfiles_recursos", ambito="persona", user_id=uid))


@bp.post("/perfiles/recursos-nuevos/reconocer")
@login_required
@admin_required
def perfiles_reconocer_recursos_nuevos():
    n = perm_asig.acknowledge_new_permission_keys()
    if n:
        flash(f"Se ocultó el aviso de {n} recurso(s) nuevo(s). Podés asignarlos cuando quieras.", "info")
    else:
        flash("No había recursos nuevos pendientes.", "info")
    ambito = (request.form.get("ambito") or "puesto").strip()
    return redirect(url_for("admin_users.perfiles_recursos", ambito=ambito))


def _normalize_username(raw: str) -> str:
    return (raw or "").strip().lower()


def _validate_new_user_inputs(username: str, password: str, password2: str) -> str | None:
    if len(username) < 3:
        return "El usuario debe tener al menos 3 caracteres."
    if not re.fullmatch(r"[a-z0-9._-]+", username):
        return "El usuario solo puede contener letras minúsculas, números, punto, guion y guion bajo."
    if len(password) < 6:
        return "La contraseña debe tener al menos 6 caracteres."
    if password != password2:
        return "Las contraseñas no coinciden."
    return None


@bp.post("/usuarios/nuevo")
@login_required
@admin_required
def create_user():
    username = _normalize_username(request.form.get("username") or "")
    nombre_completo = (request.form.get("nombre_completo") or "").strip()
    password = (request.form.get("password") or "").strip()
    password2 = (request.form.get("password2") or "").strip()
    activo = request.form.get("activo") == "1"
    rol = validate_rol_submitted(request.form.get("rol"))
    if rol is None:
        flash("Seleccioná un perfil válido.", "danger")
        return redirect(url_for("admin_users.list_users"))
    is_admin = rol == ROLE_ADMINISTRADOR

    err = _validate_new_user_inputs(username, password, password2)
    if err:
        flash(err, "danger")
        return redirect(url_for("admin_users.list_users"))

    exists = db.session.scalar(
        select(func.count()).select_from(User).where(func.lower(User.username) == username)
    )
    if int(exists or 0) > 0:
        flash("Ese nombre de usuario ya existe.", "danger")
        return redirect(url_for("admin_users.list_users"))

    u = User(
        username=username,
        nombre_completo=nombre_completo or None,
        password_hash=generate_password_hash(password),
        is_admin=bool(is_admin),
        rol=rol,
        activo=bool(activo),
    )
    from app.services.whatsapp_identity import normalize_whatsapp_e164

    wa_norm = normalize_whatsapp_e164(request.form.get("whatsapp_e164") or "") or None
    if (request.form.get("whatsapp_e164") or "").strip() and not wa_norm:
        flash("WhatsApp inválido. Usá formato internacional, ej. +54911…", "danger")
        return redirect(url_for("admin_users.list_users"))
    if wa_norm:
        dup_wa = db.session.scalar(
            select(func.count()).select_from(User).where(User.whatsapp_e164 == wa_norm)
        )
        if int(dup_wa or 0) > 0:
            flash("Ese número de WhatsApp ya está vinculado a otro usuario.", "danger")
            return redirect(url_for("admin_users.list_users"))
    u.whatsapp_e164 = wa_norm
    db.session.add(u)
    db.session.commit()
    personal_svc.sync_empleado_for_user_role(u)
    db.session.commit()
    anexo_svc.organigrama_sync_user_puestos(int(u.id), anexo_svc.organigrama_puestos_from_form(request.form))
    try:
        from app.services import sgi_difusion_mail_service as difusion_svc

        difusion_svc.notify_usuario_si_cobertura_aumenta(
            current_app._get_current_object(), int(u.id), frozenset()
        )
    except Exception:
        current_app.logger.exception("SGI: fallo mail difusión al crear usuario id=%s", u.id)
    audit_svc.record_event(
        action="user_create",
        module="admin",
        actor=current_user(),
        entity_type="user",
        entity_id=int(u.id),
        detail=truncate_plain_text(username, max_len=220),
    )
    flash("Usuario creado.", "success")
    return redirect(url_for("admin_users.edit_user", uid=u.id))


@bp.route("/usuarios/<int:uid>", methods=["GET", "POST"])
@login_required
def edit_user(uid: int):
    viewer = current_user()
    if viewer is None or not user_can_view_admin_configuration(viewer):
        flash("No tenés permiso para acceder a usuarios.", "warning")
        return redirect(url_for("main.dashboard"))

    u = db.session.get(User, uid)
    if u is None:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("admin_users.list_users"))

    viewer_may_mutate = bool(viewer.is_admin)
    admin_viewer_read_only = not viewer_may_mutate

    if request.method == "POST":
        if not viewer_may_mutate:
            flash("Solo un administrador puede modificar usuarios o contraseñas.", "warning")
            return redirect(url_for("admin_users.edit_user", uid=uid))
        act = request.form.get("action")
        if act == "core":
            from app.services import sgi_difusion_mail_service as difusion_svc

            before_sgi_docs = difusion_svc.coverage_doc_ids(int(u.id))
            new_username = _normalize_username(request.form.get("username") or "")
            if len(new_username) < 3:
                flash("El usuario debe tener al menos 3 caracteres.", "danger")
                return redirect(url_for("admin_users.edit_user", uid=uid))
            if not re.fullmatch(r"[a-z0-9._-]+", new_username):
                flash("Nombre de usuario inválido.", "danger")
                return redirect(url_for("admin_users.edit_user", uid=uid))
            dup = db.session.scalar(
                select(func.count()).select_from(User).where(
                    User.id != u.id,
                    func.lower(User.username) == new_username,
                )
            )
            if int(dup or 0) > 0:
                flash("Ese nombre de usuario ya existe.", "danger")
                return redirect(url_for("admin_users.edit_user", uid=uid))
            rol = validate_rol_submitted(request.form.get("rol"))
            if rol is None:
                flash("Seleccioná un perfil válido.", "danger")
                return redirect(url_for("admin_users.edit_user", uid=uid))
            will_admin = rol == ROLE_ADMINISTRADOR
            will_activo = request.form.get("activo") == "1"
            if not will_admin or not will_activo:
                others = db.session.scalar(
                    select(func.count()).select_from(User).where(
                        User.id != u.id,
                        User.is_admin.is_(True),
                        User.activo.is_(True),
                    )
                )
                if int(others or 0) == 0:
                    flash("Tiene que quedar al menos un administrador activo.", "danger")
                    return redirect(url_for("admin_users.edit_user", uid=uid))
            old_snapshot = {
                "username": u.username,
                "rol": u.rol,
                "activo": u.activo,
                "is_admin": u.is_admin,
            }
            u.username = new_username
            u.nombre_completo = ((request.form.get("nombre_completo") or "").strip() or None)
            u.rol = rol
            u.is_admin = will_admin
            u.activo = will_activo
            from app.services.whatsapp_identity import normalize_whatsapp_e164

            wa_raw = (request.form.get("whatsapp_e164") or "").strip()
            wa_norm = normalize_whatsapp_e164(wa_raw) or None
            if wa_raw and not wa_norm:
                flash("WhatsApp inválido. Usá formato internacional, ej. +54911…", "danger")
                return redirect(url_for("admin_users.edit_user", uid=uid))
            if wa_norm:
                dup_wa = db.session.scalar(
                    select(func.count()).select_from(User).where(
                        User.id != u.id,
                        User.whatsapp_e164 == wa_norm,
                    )
                )
                if int(dup_wa or 0) > 0:
                    flash("Ese número de WhatsApp ya está vinculado a otro usuario.", "danger")
                    return redirect(url_for("admin_users.edit_user", uid=uid))
            u.whatsapp_e164 = wa_norm
            personal_svc.sync_empleado_for_user_role(u)
            puesto_ids = anexo_svc.organigrama_puestos_from_form(request.form)
            org_pending: list = []
            anexo_svc.organigrama_sync_user_puestos(
                int(u.id), puesto_ids, commit=False, difundir_pendiente=org_pending
            )
            flags = perm_asig.perm_flags_from_form(request.form)
            base_v, base_e = perm_asig.base_perm_sets_for_role_and_puestos(u.rol, puesto_ids)
            perm_asig.replace_user_permission_overrides(u, flags, base_v, base_e)
            db.session.commit()
            anexo_svc.enviar_mails_organigrama_actualizado(org_pending)
            _refresh_session_if_self(u)
            if current_app.debug:
                v_dbg, e_dbg = perm_asig.effective_perm_lists_for_user(u)
                rows_dbg = list(
                    db.session.scalars(select(PermisoUsuario).where(PermisoUsuario.user_id == u.id)).all()
                )
                current_app.logger.debug(
                    "perm_save user_id=%s rol=%s effective_view=%s effective_edit=%s raw_rows=%s",
                    u.id,
                    u.rol,
                    v_dbg,
                    e_dbg,
                    [(r.permiso, r.habilitado, r.puede_editar) for r in rows_dbg],
                )
            try:
                difusion_svc.notify_usuario_si_cobertura_aumenta(
                    current_app._get_current_object(), int(u.id), before_sgi_docs
                )
            except Exception:
                current_app.logger.exception(
                    "SGI: fallo mail difusión al editar usuario id=%s", u.id
                )
            new_snapshot = {
                "username": u.username,
                "rol": u.rol,
                "activo": u.activo,
                "is_admin": u.is_admin,
            }
            audit_svc.record_event(
                action="user_permissions_update",
                module="admin",
                actor=viewer,
                entity_type="user",
                entity_id=u.id,
                old_value=json_preview(old_snapshot),
                new_value=json_preview(new_snapshot),
            )
            flash("Usuario actualizado.", "success")
            return redirect(url_for("admin_users.edit_user", uid=uid))
        if act == "password":
            p1 = (request.form.get("password") or "").strip()
            p2 = (request.form.get("password2") or "").strip()
            if len(p1) < 6:
                flash("La contraseña debe tener al menos 6 caracteres.", "danger")
            elif p1 != p2:
                flash("Las contraseñas no coinciden.", "danger")
            else:
                u.password_hash = generate_password_hash(p1)
                db.session.commit()
                audit_svc.record_event(
                    action="user_password_change",
                    module="admin",
                    actor=viewer,
                    entity_type="user",
                    entity_id=u.id,
                )
                flash("Contraseña actualizada.", "success")
            return redirect(url_for("admin_users.edit_user", uid=uid))

    perms_set: set[str] = set()
    perms_edit_set: set[str] = set()
    role_view_set: set[str] = set()
    role_edit_set: set[str] = set()
    puesto_view_set: set[str] = set()
    puesto_edit_set: set[str] = set()
    comun_view_set: set[str] = set()
    comun_edit_set: set[str] = set()
    hide_perm_grid = perm_asig.user_uses_fixed_perm_template(u) and not u.is_admin
    if u.is_admin:
        hide_perm_grid = True
    else:
        puesto_ids = anexo_svc.organigrama_node_ids_for_user(u.id)
        puesto_view_set, puesto_edit_set = perm_asig.view_edit_for_puestos(puesto_ids)
        comun_view_set, comun_edit_set = perm_asig.comunes_perm_sets()
        role_view_set, role_edit_set = role_template_perm_sets(u.rol)
        view_l, edit_l = perm_asig.effective_perm_lists_for_user(u)
        perms_set = set(view_l)
        perms_edit_set = set(edit_l)
    empleado_personal = (
        personal_svc.get_empleado_by_user_id(u.id) if personal_svc.user_requires_legajo(u) else None
    )
    if empleado_personal is None and personal_svc.user_requires_legajo(u):
        personal_svc.ensure_empleado_for_user(u)
        empleado_personal = personal_svc.get_empleado_by_user_id(u.id)
    return render_template(
        "admin/user_edit.html",
        edit_user=u,
        empleado_personal=empleado_personal,
        empleado_legajo_status=personal_svc.legajo_status_for_empleado(empleado_personal),
        user_requires_legajo=personal_svc.user_requires_legajo,
        hide_perm_grid=hide_perm_grid,
        admin_viewer_read_only=admin_viewer_read_only,
        permission_labels=PERMISSION_LABELS,
        permission_tree=PERMISSION_TREE,
        perms_set=perms_set,
        perms_edit_set=perms_edit_set,
        role_view_set=role_view_set,
        role_edit_set=role_edit_set,
        puesto_view_set=puesto_view_set,
        puesto_edit_set=puesto_edit_set,
        comun_view_set=comun_view_set,
        comun_edit_set=comun_edit_set,
        user_roles_ordered=USER_ROLES_ORDERED,
        role_labels=ROLE_LABELS,
        organigrama_puestos=anexo_svc.organigrama_puesto_opciones(),
        organigrama_puestos_selected=anexo_svc.organigrama_node_ids_for_user(u.id),
        permisos_recursos_nuevos=perm_asig.new_unassigned_resources(),
    )


@bp.post("/usuarios/<int:uid>/eliminar")
@login_required
@admin_required
def delete_user(uid: int):
    if current_user() and current_user().id == uid:
        flash("No podés borrarte a vos mismo.", "danger")
        return redirect(url_for("admin_users.list_users"))
    u = db.session.get(User, uid)
    if u:
        uname = u.username
        uid_del = int(u.id)
        db.session.delete(u)
        db.session.commit()
        audit_svc.record_event(
            action="user_delete",
            module="admin",
            actor=current_user(),
            entity_type="user",
            entity_id=uid_del,
            detail=truncate_plain_text(uname or "", max_len=220),
        )
        flash("Usuario eliminado.", "info")
    return redirect(url_for("admin_users.list_users"))


@bp.get("/equipos")
@login_required
def equipos_list():
    u = current_user()
    if u is None or not user_can_view_admin_configuration(u):
        flash("No tenés permiso para acceder a equipos.", "warning")
        return redirect(url_for("main.dashboard"))
    rows = db.session.scalars(select(Equipo).order_by(Equipo.nombre_equipo)).all()
    return render_template("admin/equipos.html", equipos=rows, viewer_may_manage_users=bool(u.is_admin))


@bp.post("/equipos/nuevo")
@login_required
@admin_required
def equipo_nuevo():
    nombre = (request.form.get("nombre_equipo") or "").strip()
    desc = (request.form.get("descripcion") or "").strip()
    if nombre:
        db.session.add(
            Equipo(
                nombre_equipo=nombre,
                descripcion=desc,
                activo=True,
                created_at_iso=now_operacion_local_iso_seconds(),
            )
        )
        db.session.commit()
        flash("Equipo creado.", "success")
    return redirect(url_for("admin_users.equipos_list"))


@bp.post("/equipos/<int:eid>/toggle")
@login_required
@admin_required
def equipo_toggle(eid: int):
    e = db.session.get(Equipo, eid)
    if e:
        e.activo = not e.activo
        db.session.commit()
        flash("Estado actualizado.", "info")
    return redirect(url_for("admin_users.equipos_list"))


@bp.get("/avisos-correo")
@login_required
def deadline_alert_emails():
    u = current_user()
    if u is None or not user_can_view_admin_configuration(u):
        flash("No tenés permiso para acceder a esta configuración.", "warning")
        return redirect(url_for("main.dashboard"))
    rows = list_emails_ordered()
    merged = merged_recipient_addresses(current_app)
    env_addrs = [str(x).strip() for x in (current_app.config.get("DEADLINE_ALERT_EMAIL_TO") or []) if str(x).strip()]
    plant_stop_env = [
        str(x).strip()
        for x in (current_app.config.get("PLANT_STOP_ALERT_EMAIL_TO") or [])
        if str(x).strip()
    ]
    stock_critical_env = [
        str(x).strip()
        for x in (current_app.config.get("STOCK_CRITICAL_ALERT_EMAIL_TO") or [])
        if str(x).strip()
    ]
    return render_template(
        "admin/avisos_correo.html",
        db_rows=rows,
        merged_recipients=merged,
        env_addresses=env_addrs,
        viewer_may_edit_deadline_mails=bool(u.is_admin),
        smtp_configured=is_mail_fully_configured(current_app),
        smtp_diagnostic=smtp_diagnostic_summary(current_app),
        viewer_is_admin=bool(u.is_admin),
        plant_stop_db_rows=plant_stop_svc.list_alert_emails_ordered() if u.is_admin else [],
        plant_stop_merged=plant_stop_svc.merged_plant_stop_recipients(current_app) if u.is_admin else [],
        plant_stop_env_addresses=plant_stop_env if u.is_admin else [],
        stock_critical_db_rows=stock_alert_svc.list_emails_ordered() if u.is_admin else [],
        stock_critical_merged=stock_alert_svc.merged_recipient_addresses(current_app) if u.is_admin else [],
        stock_critical_env_addresses=stock_critical_env if u.is_admin else [],
    )


@bp.post("/avisos-correo/enviar-vencimientos")
@login_required
@admin_required
def vencimientos_reminders_send():
    if not is_mail_fully_configured(current_app):
        flash("SMTP no configurado: revisá SMTP_HOST y MAIL_FROM en el servidor.", "warning")
        return redirect(url_for("admin_users.deadline_alert_emails"))
    out = run_vencimiento_reminders(current_app, dry_run=False)
    msg = out.get("message") or "Proceso de avisos de vencimientos finalizado."
    if out.get("errors"):
        flash(f"{msg} Hubo {len(out['errors'])} error(es).", "warning")
    elif int(out.get("emails_sent") or 0) > 0:
        flash(msg, "success")
    else:
        flash(msg, "info")
    return redirect(url_for("admin_users.deadline_alert_emails"))


@bp.post("/avisos-correo/enviar-epp-pendientes")
@login_required
@admin_required
def entrega_epp_reminders_send():
    if not is_mail_fully_configured(current_app):
        flash("SMTP no configurado: revisá SMTP_HOST y MAIL_FROM en el servidor.", "warning")
        return redirect(url_for("admin_users.deadline_alert_emails"))
    out = run_entrega_epp_reminders(current_app, dry_run=False)
    msg = out.get("message") or "Proceso de recordatorios EPP finalizado."
    if out.get("errors"):
        flash(f"{msg} Hubo {len(out['errors'])} error(es).", "warning")
    elif int(out.get("emails_sent") or 0) > 0:
        flash(msg, "success")
    else:
        flash(msg, "info")
    return redirect(url_for("admin_users.deadline_alert_emails"))


@bp.post("/avisos-correo/sgi-reenviar-avisos")
@login_required
@admin_required
def sgi_workflow_reminders_resend():
    if not is_mail_fully_configured(current_app):
        flash("SMTP no configurado: revisá SMTP_HOST y MAIL_FROM en el servidor.", "warning")
        return redirect(url_for("admin_users.deadline_alert_emails"))
    from app.services import sgi_procedimiento_service as proc_svc

    out = proc_svc.reenviar_avisos_pendientes(current_app, dry_run=False)
    msg = out.get("message") or "Proceso de avisos SGC finalizado."
    sent = int(out.get("sent") or 0)
    failed = int(out.get("failed") or 0)
    if sent > 0 and not failed:
        flash(msg, "success")
    elif sent > 0 or failed > 0:
        flash(msg, "warning")
    else:
        flash(msg, "info")
    return redirect(url_for("admin_users.deadline_alert_emails"))


@bp.post("/avisos-correo/probar-envio")
@login_required
@admin_required
def smtp_probe_send():
    addr = normalize_validate_email(request.form.get("test_email"))
    if addr is None:
        flash("Ingresá un correo electrónico válido para la prueba.", "danger")
        return redirect(url_for("admin_users.deadline_alert_emails"))
    if not is_mail_fully_configured(current_app):
        flash("SMTP no configurado: revisá SMTP_HOST y MAIL_FROM en el servidor.", "warning")
        return redirect(url_for("admin_users.deadline_alert_emails"))
    try:
        enviar_mail(
            current_app,
            destinatarios=[addr],
            asunto="QDV — Prueba de envío SMTP",
            cuerpo_html="<p>Mensaje de prueba. La infraestructura SMTP está operativa.</p>",
            cuerpo_texto="Mensaje de prueba. La infraestructura SMTP está operativa.",
        )
        flash(f"Correo de prueba enviado a {addr}.", "success")
    except Exception as exc:
        flash(f"No se pudo enviar la prueba: {exc}", "danger")
    return redirect(url_for("admin_users.deadline_alert_emails"))


@bp.post("/avisos-correo/parada-planta/agregar")
@login_required
@admin_required
def plant_stop_alert_email_add():
    ok, msg = plant_stop_svc.add_alert_email(request.form.get("email"))
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("admin_users.deadline_alert_emails"))


@bp.post("/avisos-correo/parada-planta/<int:eid>/eliminar")
@login_required
@admin_required
def plant_stop_alert_email_delete(eid: int):
    removed = plant_stop_svc.delete_alert_email_row(eid)
    if removed is None:
        flash("Correo no encontrado.", "warning")
    else:
        flash("Correo de paradas de planta eliminado.", "info")
    return redirect(url_for("admin_users.deadline_alert_emails"))


@bp.post("/avisos-correo/stock-critico/agregar")
@login_required
@admin_required
def stock_critical_alert_email_add():
    ok, msg = stock_alert_svc.add_email(request.form.get("email"))
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("admin_users.deadline_alert_emails"))


@bp.post("/avisos-correo/stock-critico/<int:eid>/eliminar")
@login_required
@admin_required
def stock_critical_alert_email_delete(eid: int):
    removed = stock_alert_svc.delete_email_row(eid)
    if removed is None:
        flash("Correo no encontrado.", "warning")
    else:
        flash("Correo de stock crítico eliminado.", "info")
    return redirect(url_for("admin_users.deadline_alert_emails"))


@bp.post("/avisos-correo/agregar")
@login_required
@admin_required
def deadline_alert_email_add():
    ok, msg = add_email(request.form.get("email"))
    flash(msg, "success" if ok else "danger")
    if ok:
        audit_svc.record_event(
            action="deadline_alert_email_add",
            module="admin",
            actor=current_user(),
            entity_type="deadline_alert_email",
            detail=truncate_plain_text((request.form.get("email") or "").strip().lower(), max_len=220),
        )
    return redirect(url_for("admin_users.deadline_alert_emails"))


@bp.post("/avisos-correo/<int:eid>/eliminar")
@login_required
@admin_required
def deadline_alert_email_delete(eid: int):
    removed = delete_email_row(eid)
    if removed is None:
        flash("Correo no encontrado.", "warning")
        return redirect(url_for("admin_users.deadline_alert_emails"))
    audit_svc.record_event(
        action="deadline_alert_email_delete",
        module="admin",
        actor=current_user(),
        entity_type="deadline_alert_email",
        detail=truncate_plain_text(removed or "", max_len=220),
    )
    flash("Correo eliminado.", "info")
    return redirect(url_for("admin_users.deadline_alert_emails"))
