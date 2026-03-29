from __future__ import annotations

import click
from flask import Flask
from sqlalchemy import func as sa_func
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.argument("username")
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="Contraseña del administrador (no dejar en historial: usar prompt).",
    )
    def create_admin(username: str, password: str) -> None:
        """Crea un usuario administrador activo (username se guarda en minúsculas)."""
        name = username.strip().lower()
        if not name:
            raise click.ClickException("El nombre de usuario no puede estar vacío.")
        if not password:
            raise click.ClickException("La contraseña no puede estar vacía.")

        exists = db.session.execute(
            select(User).where(sa_func.lower(User.username) == name)
        ).scalar_one_or_none()
        if exists is not None:
            raise click.ClickException(f"Ya existe un usuario con nombre {name!r}.")

        u = User(
            username=name,
            password_hash=generate_password_hash(password),
            is_admin=True,
            activo=True,
        )
        db.session.add(u)
        db.session.commit()
        click.echo(f"Administrador creado: {name} (id={u.id})")

    @app.cli.command("list-users")
    def list_users() -> None:
        """Lista usuarios de la base web (misma SQLite que usa run.py)."""
        rows = db.session.scalars(select(User).order_by(User.username)).all()
        if not rows:
            click.echo("No hay usuarios. Creá uno con: python -m flask --app run create-admin TU_NOMBRE")
            return
        click.echo("id\tusuario\t\tadmin\tactivo")
        for u in rows:
            click.echo(f"{u.id}\t{u.username}\t\t{u.is_admin}\t{u.activo}")

    @app.cli.command("reset-password")
    @click.argument("username")
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="Nueva contraseña.",
    )
    def reset_password(username: str, password: str) -> None:
        """Asigna una nueva contraseña a un usuario existente (nombre sin importar mayúsculas)."""
        name = username.strip().lower()
        u = db.session.execute(
            select(User).where(sa_func.lower(User.username) == name)
        ).scalar_one_or_none()
        if u is None:
            raise click.ClickException(
                f"No existe el usuario {name!r}. Ejecutá: python -m flask --app run list-users"
            )
        if not password:
            raise click.ClickException("La contraseña no puede estar vacía.")
        u.password_hash = generate_password_hash(password)
        db.session.commit()
        click.echo(f"Contraseña actualizada para: {u.username}")
