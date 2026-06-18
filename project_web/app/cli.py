from __future__ import annotations

import click
from flask import Flask
from sqlalchemy import func as sa_func
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User
from app.services.deadline_reminder_service import run_deadline_reminders
from app.services.personal_epp_reminder_service import run_entrega_epp_reminders
from app.services.vencimiento_reminder_service import run_vencimiento_reminders
from app.user_roles import ROLE_ADMINISTRADOR


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
            rol=ROLE_ADMINISTRADOR,
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
        click.echo("id\tusuario\t\tadmin\trol\tactivo")
        for u in rows:
            r = getattr(u, "rol", "") or ""
            click.echo(f"{u.id}\t{u.username}\t\t{u.is_admin}\t{r}\t{u.activo}")

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

    @app.cli.command("send-deadline-reminders")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Mostrar ítems y cuerpo del correo sin enviar ni registrar.",
    )
    def send_deadline_reminders(dry_run: bool) -> None:
        """Avisos por mail: planificación, mantenimiento, vencimientos y entregas EPP/ropa pendientes.

        Configurar SMTP_* , MAIL_FROM y destinatarios en Administración → Avisos por correo / DEADLINE_ALERT_EMAIL_TO.
        Cron diario recomendado. Opcional: DEADLINE_REMINDER_DAYS_BEFORE (planificación/mantenimiento; por defecto 30).
        Los avisos EPP se envían al email del legajo del empleado al registrar la entrega y como recordatorio diario.
        """
        with app.app_context():
            out = run_deadline_reminders(app, dry_run=dry_run)
            out_v = run_vencimiento_reminders(app, dry_run=dry_run)
            out_epp = run_entrega_epp_reminders(app, dry_run=dry_run)
        click.echo(out.get("message") or "")
        click.echo(
            f"Fecha operación: {out.get('today')} · Días de anticipación: {out.get('days_before')} · "
            f"Planificación: {out.get('planificacion_count')} · Mantenimiento: {out.get('mantenimiento_count')}"
        )
        click.echo(out_v.get("message") or "")
        click.echo(
            f"Vencimientos · anticipación: {out_v.get('days_before')} días · candidatos: {out_v.get('candidates')} · "
            f"intentados: {out_v.get('emails_attempted')} · enviados: {out_v.get('emails_sent')}"
        )
        click.echo(out_epp.get("message") or "")
        click.echo(
            f"EPP/ropa pendientes · empleados: {out_epp.get('empleados_con_pendientes')} · "
            f"intentados: {out_epp.get('emails_attempted')} · enviados: {out_epp.get('emails_sent')}"
        )
        if dry_run and out.get("preview_body"):
            click.echo("--- Planificación/Mantenimiento: asunto ---")
            click.echo(out.get("preview_subject") or "")
            click.echo("--- Planificación/Mantenimiento: cuerpo ---")
            click.echo(out.get("preview_body"))
