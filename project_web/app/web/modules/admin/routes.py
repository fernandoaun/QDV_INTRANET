from __future__ import annotations

import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import delete, func, select
from werkzeug.security import generate_password_hash

from app.auth_utils import admin_required, current_user, login_required, user_can_view_admin_configuration
from app.constants import PERMISSION_FORM_KEYS, PERMISSION_KEYS, PERMISSION_LABELS, PERMISSION_TREE
from app.extensions import db
from app.models import Equipo, PermisoUsuario, User
from app.security_http import truncate_plain_text
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
from app.services.mail_service import enviar_mail, is_mail_fully_configured, smtp_diagnostic_summary
from app.services.personal_epp_reminder_service import run_entrega_epp_reminders
from app.services.vencimiento_reminder_service import run_vencimiento_reminders
from app.utils.datetime_operacion import now_operacion_local_iso_seconds
from app.user_roles import (
    ROLE_ADMINISTRADOR,
    ROLE_LABORATORISTA,
    ROLE_LABELS,
    ROLE_SGI,
    ROLE_SOLO_LECTURA_TOTAL,
    USER_ROLES_ORDERED,
    compute_session_perm_lists,
    normalize_stored_rol,
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
    )


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
    db.session.add(u)
    db.session.commit()
    personal_svc.sync_empleado_for_user_role(u)
    db.session.commit()
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
            personal_svc.sync_empleado_for_user_role(u)
            db.session.execute(delete(PermisoUsuario).where(PermisoUsuario.user_id == u.id))
            if not u.is_admin and normalize_stored_rol(u.rol) not in (
                ROLE_LABORATORISTA,
                ROLE_SOLO_LECTURA_TOTAL,
                ROLE_SGI,
            ):
                bv, be = role_template_perm_sets(u.rol)
                for key in PERMISSION_FORM_KEYS:
                    if key not in PERMISSION_KEYS:
                        continue
                    fv = request.form.get(f"permv_{key}") == "1"
                    fe = request.form.get(f"perme_{key}") == "1"
                    if fe and not fv:
                        fe = False
                    in_bv = key in bv
                    in_be = key in be
                    if not fv:
                        if in_bv:
                            db.session.add(
                                PermisoUsuario(
                                    user_id=u.id,
                                    permiso=key,
                                    habilitado=False,
                                    puede_editar=False,
                                )
                            )
                        continue
                    if not in_bv:
                        db.session.add(
                            PermisoUsuario(
                                user_id=u.id,
                                permiso=key,
                                habilitado=True,
                                puede_editar=fe,
                            )
                        )
                        continue
                    default_edit = in_be
                    if fe != default_edit:
                        db.session.add(
                            PermisoUsuario(
                                user_id=u.id,
                                permiso=key,
                                habilitado=True,
                                puede_editar=fe,
                            )
                        )
            db.session.commit()
            if current_app.debug:
                rows_dbg = list(
                    db.session.scalars(select(PermisoUsuario).where(PermisoUsuario.user_id == u.id)).all()
                )
                v_dbg, e_dbg = compute_session_perm_lists(u.rol, rows_dbg)
                current_app.logger.debug(
                    "perm_save user_id=%s rol=%s effective_view=%s effective_edit=%s raw_rows=%s",
                    u.id,
                    u.rol,
                    v_dbg,
                    e_dbg,
                    [(r.permiso, r.habilitado, r.puede_editar) for r in rows_dbg],
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
                old_value=audit_svc.json_preview(old_snapshot),
                new_value=audit_svc.json_preview(new_snapshot),
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
    if not u.is_admin:
        rows = list(db.session.scalars(select(PermisoUsuario).where(PermisoUsuario.user_id == u.id)).all())
        view_l, edit_l = compute_session_perm_lists(u.rol, rows)
        perms_set = set(view_l)
        perms_edit_set = set(edit_l)
    hide_perm_grid = (not u.is_admin) and normalize_stored_rol(u.rol) in (
        ROLE_LABORATORISTA,
        ROLE_SOLO_LECTURA_TOTAL,
        ROLE_SGI,
    )
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
        permission_keys=PERMISSION_KEYS,
        permission_labels=PERMISSION_LABELS,
        permission_tree=PERMISSION_TREE,
        perms_set=perms_set,
        perms_edit_set=perms_edit_set,
        user_roles_ordered=USER_ROLES_ORDERED,
        role_labels=ROLE_LABELS,
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
    msg = out.get("message") or "Proceso de avisos SGI finalizado."
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
