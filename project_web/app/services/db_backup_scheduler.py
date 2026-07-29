"""
Programador en segundo plano: respaldo semanal de la BD sin cron externo.

Mientras la app est├⌐ en ejecuci├│n, revisa peri├│dicamente si ya pas├│ el intervalo
(por defecto 7 d├¡as) y genera una copia. El primer ciclo tras el arranque corre
si nunca hubo respaldo o si ya venci├│ el plazo.
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


def should_start_db_backup_scheduler(app: Any) -> bool:
    if app.config.get("TESTING"):
        return False
    if not app.config.get("DB_BACKUP_ENABLED", True):
        return False
    if not app.config.get("DB_BACKUP_SCHEDULER", True):
        return False
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def _lock_file_path(app: Any) -> Path:
    p = Path(app.instance_path) / "locks"
    p.mkdir(parents=True, exist_ok=True)
    return p / "db_backup_scheduler.lock"


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
            log.debug("Respaldo BD: otro proceso ya est├í ejecutando el ciclo.")
            return
        with app.app_context():
            fn()
    finally:
        handle.close()


def _run_backup_cycle(app: Any) -> None:
    from app.services.db_backup_service import run_database_backup

    out = run_database_backup(app, force=False)
    if out.get("skipped"):
        log.debug("Respaldo BD omitido: %s", out.get("message") or "")
        return
    if out.get("ok"):
        log.info("Respaldo BD autom├ítico: %s", out.get("filename") or out.get("message"))
    else:
        log.warning("Respaldo BD autom├ítico fall├│: %s", out.get("message") or "")


def _scheduler_loop(app: Any) -> None:
    startup_delay = max(5, int(app.config.get("DB_BACKUP_STARTUP_DELAY_SEC") or 20))
    check_hours = max(1, int(app.config.get("DB_BACKUP_CHECK_INTERVAL_HOURS") or 12))
    interval_sec = check_hours * 3600

    time.sleep(startup_delay)
    while True:
        try:
            _run_exclusive(app, lambda: _run_backup_cycle(app))
        except Exception:
            log.exception("Fallo en ciclo autom├ítico de respaldo de BD")
        time.sleep(interval_sec)


def init_db_backup_scheduler(app: Any) -> None:
    global _scheduler_started
    with _scheduler_guard:
        if _scheduler_started:
            return
        if not should_start_db_backup_scheduler(app):
            return
        _scheduler_started = True

    days = max(1, int(app.config.get("DB_BACKUP_INTERVAL_DAYS") or 7))
    t = threading.Thread(
        target=_scheduler_loop,
        args=(app,),
        daemon=True,
        name="db-backup-scheduler",
    )
    t.start()
    app.logger.info(
        "Respaldo semanal de BD activo (cada %s d├¡a(s); revisi├│n peri├│dica en segundo plano).",
        days,
    )
