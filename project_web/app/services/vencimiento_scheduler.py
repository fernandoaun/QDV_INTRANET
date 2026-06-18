"""
Programador en segundo plano: avisos de vencimientos sin cron externo.

Mientras la aplicación web esté en ejecución, revisa periódicamente los ítems en
ventana de anticipación (p. ej. 30 días) y envía el correo una vez por registro.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_guard = threading.Lock()


def should_start_vencimiento_scheduler(app: Any) -> bool:
    if app.config.get("TESTING"):
        return False
    if not app.config.get("VENCIMIENTO_AUTO_MAIL_ENABLED", True):
        return False
    if not app.config.get("VENCIMIENTO_AUTO_MAIL_SCHEDULER", True):
        return False
    # Con el reloader de Flask, solo el proceso hijo debe arrancar el hilo.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def _lock_file_path(app: Any) -> Path:
    p = Path(app.instance_path) / "locks"
    p.mkdir(parents=True, exist_ok=True)
    return p / "vencimiento_mail_scheduler.lock"


def _run_exclusive(app: Any, fn: Callable[[], None]) -> None:
    path = _lock_file_path(app)
    handle = open(path, "a+", encoding="utf-8")
    try:
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log.debug("Avisos de vencimientos: otro proceso ya está ejecutando el ciclo.")
            return
        with app.app_context():
            fn()
    finally:
        handle.close()


def _run_reminders(app: Any) -> None:
    from app.services.mail_service import is_mail_fully_configured
    from app.services.personal_birthday_reminder_service import run_birthday_reminders
    from app.services.vencimiento_reminder_service import run_vencimiento_reminders

    if not is_mail_fully_configured(app):
        return
    out = run_vencimiento_reminders(app, dry_run=False)
    sent = int(out.get("emails_sent") or 0)
    candidates = int(out.get("candidates") or 0)
    if sent or candidates:
        log.info(
            "Avisos de vencimientos: candidatos=%s enviados=%s · %s",
            candidates,
            sent,
            out.get("message") or "",
        )
    elif out.get("errors"):
        log.warning("Avisos de vencimientos con errores: %s", out.get("errors"))

    out_b = run_birthday_reminders(app, dry_run=False)
    if int(out_b.get("cumpleaneros") or 0) > 0:
        log.info("Avisos de cumpleaños: %s", out_b.get("message") or "")
    elif out_b.get("errors"):
        log.warning("Avisos de cumpleaños con errores: %s", out_b.get("errors"))


def _scheduler_loop(app: Any) -> None:
    startup_delay = max(5, int(app.config.get("VENCIMIENTO_AUTO_MAIL_STARTUP_DELAY_SEC") or 30))
    interval_hours = max(1, int(app.config.get("VENCIMIENTO_AUTO_MAIL_INTERVAL_HOURS") or 6))
    interval_sec = interval_hours * 3600

    time.sleep(startup_delay)
    while True:
        try:
            _run_exclusive(app, lambda: _run_reminders(app))
        except Exception:
            log.exception("Fallo en ciclo automático de avisos de vencimientos")
        time.sleep(interval_sec)


def init_vencimiento_mail_scheduler(app: Any) -> None:
    global _scheduler_started
    with _scheduler_guard:
        if _scheduler_started:
            return
        if not should_start_vencimiento_scheduler(app):
            return
        _scheduler_started = True

    interval = max(1, int(app.config.get("VENCIMIENTO_AUTO_MAIL_INTERVAL_HOURS") or 6))
    t = threading.Thread(
        target=_scheduler_loop,
        args=(app,),
        daemon=True,
        name="vencimiento-mail-scheduler",
    )
    t.start()
    app.logger.info(
        "Avisos de vencimientos automáticos activos (cada %s h, sin cron manual).",
        interval,
    )
