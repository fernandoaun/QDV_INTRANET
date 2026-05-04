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
from app.utils.datetime_operacion import now_operacion_local_iso_seconds
from app.user_roles import (
    ROLE_ADMINISTRADOR,
    ROLE_LABORATORISTA,
    ROLE_LABELS,
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
    return render_template("admin/users_list.html", users=rows, viewer_may_manage_users=bool(u.is_admin))


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
            db.session.execute(delete(PermisoUsuario).where(PermisoUsuario.user_id == u.id))
            if not u.is_admin and normalize_stored_rol(u.rol) not in (
                ROLE_LABORATORISTA,
                ROLE_SOLO_LECTURA_TOTAL,
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
    )
    return render_template(
        "admin/user_edit.html",
        edit_user=u,
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
