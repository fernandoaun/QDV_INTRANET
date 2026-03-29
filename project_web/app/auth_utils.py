from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import flash, redirect, request, session, url_for

from app.extensions import db
from app.models import PermisoUsuario, User
from app.constants import PERMISSION_KEYS

from sqlalchemy import select

F = TypeVar("F", bound=Callable[..., Any])


def current_user() -> User | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, int(uid))


def set_session_for_user(user: User) -> None:
    session["user_id"] = user.id
    session.permanent = True
    if user.is_admin:
        session["perms"] = list(PERMISSION_KEYS)
    else:
        rows = db.session.scalars(
            select(PermisoUsuario).where(
                PermisoUsuario.user_id == user.id,
                PermisoUsuario.habilitado.is_(True),
            )
        ).all()
        session["perms"] = [r.permiso for r in rows]


def user_can(user: User | None, perm: str) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return perm in set(session.get("perms", []))


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.url))
        if not user.activo:
            session.clear()
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return cast(F, wrapped)


def admin_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.url))
        if not user.activo or not user.is_admin:
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)

    return cast(F, wrapped)


def permission_required(perm: str):
    def decorator(view: F) -> F:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.login", next=request.url))
            if not user_can(user, perm):
                flash("No tenés permiso para acceder a esta sección.", "warning")
                return redirect(url_for("main.dashboard"))
            return view(*args, **kwargs)

        return cast(F, wrapped)

    return decorator
