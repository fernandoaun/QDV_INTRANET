from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import delete, func, select
from werkzeug.security import generate_password_hash

from app.auth_utils import admin_required, current_user, login_required
from app.constants import PERMISSION_KEYS, PERMISSION_LABELS
from app.extensions import db
from app.models import Equipo, PermisoUsuario, User

bp = Blueprint("admin_users", __name__, url_prefix="/admin")


@bp.get("/usuarios")
@login_required
@admin_required
def list_users():
    rows = db.session.scalars(select(User).order_by(User.username)).all()
    return render_template("admin/users_list.html", users=rows)


@bp.route("/usuarios/<int:uid>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(uid: int):
    u = db.session.get(User, uid)
    if u is None:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("admin_users.list_users"))

    if request.method == "POST":
        act = request.form.get("action")
        if act == "core":
            will_admin = request.form.get("is_admin") == "1"
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
            u.username = (request.form.get("username") or "").strip().lower()
            u.is_admin = will_admin
            u.activo = will_activo
            db.session.execute(delete(PermisoUsuario).where(PermisoUsuario.user_id == u.id))
            if not u.is_admin:
                for key in PERMISSION_KEYS:
                    if request.form.get(f"perm_{key}") == "1":
                        db.session.add(PermisoUsuario(user_id=u.id, permiso=key, habilitado=True))
            db.session.commit()
            flash("Usuario actualizado.", "success")
            return redirect(url_for("admin_users.list_users"))
        if act == "password":
            p1 = (request.form.get("password") or "").strip()
            p2 = (request.form.get("password2") or "").strip()
            if len(p1) < 4:
                flash("La contraseña es muy corta.", "danger")
            elif p1 != p2:
                flash("Las contraseñas no coinciden.", "danger")
            else:
                u.password_hash = generate_password_hash(p1)
                db.session.commit()
                flash("Contraseña actualizada.", "success")
            return redirect(url_for("admin_users.edit_user", uid=uid))

    perms_set = set()
    if not u.is_admin:
        for r in db.session.scalars(select(PermisoUsuario).where(PermisoUsuario.user_id == u.id)).all():
            if r.habilitado:
                perms_set.add(r.permiso)
    return render_template(
        "admin/user_edit.html",
        edit_user=u,
        permission_keys=PERMISSION_KEYS,
        permission_labels=PERMISSION_LABELS,
        perms_set=perms_set,
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
        db.session.delete(u)
        db.session.commit()
        flash("Usuario eliminado.", "info")
    return redirect(url_for("admin_users.list_users"))


@bp.get("/equipos")
@login_required
@admin_required
def equipos_list():
    rows = db.session.scalars(select(Equipo).order_by(Equipo.nombre_equipo)).all()
    return render_template("admin/equipos.html", equipos=rows)


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
                created_at_iso=datetime.now().isoformat(timespec="seconds"),
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
