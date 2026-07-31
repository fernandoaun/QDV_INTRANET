"""
Respaldo diario de la base de datos, sin interrumpir a quienes usan la app.

- SQLite: API online ``Connection.backup`` (copia coherente mientras se sigue leyendo/escribiendo).
- PostgreSQL: ``pg_dump`` si está disponible en el PATH (también en caliente).

Los archivos viven fuera de la BD activa; restaurar es un paso aparte y manual.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

log = logging.getLogger(__name__)

_META_NAME = "last_backup.json"
_ISO_FMT = "%Y-%m-%dT%H:%M:%S%z"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+0000"
        if len(s) >= 5 and (s[-5] in "+-" and s[-3] != ":"):
            return datetime.strptime(s, _ISO_FMT)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _format_display(dt: datetime | None) -> str:
    if dt is None:
        return ""
    local = dt.astimezone()
    return local.strftime("%d/%m/%Y %H:%M")


def _format_short(dt: datetime | None) -> str:
    if dt is None:
        return ""
    local = dt.astimezone()
    return local.strftime("%d/%m/%Y")


def backup_dir(app: Any) -> Path:
    """Carpeta de respaldos: DB_BACKUP_DIR, o APP_UPLOAD_ROOT/db_backups, o instance/db_backups."""
    configured = (app.config.get("DB_BACKUP_DIR") or "").strip()
    if configured:
        path = Path(configured)
    else:
        upload_root = (app.config.get("APP_UPLOAD_ROOT") or "").strip()
        if upload_root:
            path = Path(upload_root) / "db_backups"
        else:
            path = Path(app.instance_path) / "db_backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def meta_path(app: Any) -> Path:
    return backup_dir(app) / _META_NAME


def load_last_backup_meta(app: Any) -> dict[str, Any] | None:
    path = meta_path(app)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def save_last_backup_meta(app: Any, meta: dict[str, Any]) -> None:
    path = meta_path(app)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def database_uri(app: Any) -> str:
    return (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()


def sqlite_file_from_uri(uri: str) -> Path | None:
    """Ruta del archivo SQLite, o None si es memoria / no-SQLite."""
    if not uri.lower().startswith("sqlite:"):
        return None
    if ":memory:" in uri.lower():
        return None
    # sqlite:///C:/path  o  sqlite:////abs/path  o  sqlite:///rel
    rest = uri.split("://", 1)[-1]
    if rest.startswith("/") and not rest.startswith("///"):
        # sqlalchemy: sqlite:///foo -> /foo ; sqlite:////abs -> //abs
        if rest.startswith("//"):
            rest = rest[1:]  # /abs
        elif len(rest) >= 3 and rest[2] == ":":
            # /C:/Windows → C:/Windows
            rest = rest[1:]
    path = Path(unquote(rest))
    return path if str(path) else None


def is_backup_due(app: Any) -> bool:
    if not app.config.get("DB_BACKUP_ENABLED", True):
        return False
    meta = load_last_backup_meta(app)
    if not meta or meta.get("ok") is not True:
        return True
    last = _parse_iso(meta.get("finished_at_iso") or meta.get("created_at_iso"))
    if last is None:
        return True
    interval_days = max(1, int(app.config.get("DB_BACKUP_INTERVAL_DAYS") or 1))
    return _now_utc() >= last + timedelta(days=interval_days)


def _prune_old_backups(directory: Path, keep: int) -> None:
    keep = max(1, keep)
    pattern = re.compile(r"^qdv_backup_\d{8}_\d{6}\.(db|dump|sql)(\.gz)?$", re.I)
    files = sorted(
        (p for p in directory.iterdir() if p.is_file() and pattern.match(p.name)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            log.warning("No se pudo eliminar respaldo antiguo: %s", old)


def _backup_sqlite(src: Path, dest: Path) -> None:
    """Copia online: la BD sigue disponible para lecturas/escrituras."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src_con = sqlite3.connect(str(src))
    try:
        dst_con = sqlite3.connect(str(dest))
        try:
            with dst_con:
                src_con.backup(dst_con)
        finally:
            dst_con.close()
    finally:
        src_con.close()


def _pg_dump_available() -> str | None:
    return shutil.which("pg_dump")


def _backup_postgres(uri: str, dest: Path) -> None:
    """Dump en caliente vía pg_dump (formato custom)."""
    exe = _pg_dump_available()
    if not exe:
        raise RuntimeError(
            "PostgreSQL: no se encontró pg_dump en el PATH. "
            "Instalá las herramientas cliente de Postgres o usá el respaldo del proveedor (Render/Railway)."
        )
    # Normalizar a URL que entiende pg_dump (sin +psycopg2)
    url = uri.replace("postgresql+psycopg2://", "postgresql://", 1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    env = os.environ.copy()
    # Evitar prompts interactivos
    env.setdefault("PGCONNECT_TIMEOUT", "30")
    result = subprocess.run(
        [
            exe,
            "--no-owner",
            "--no-acl",
            "--format=custom",
            "--file",
            str(dest),
            url,
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=max(60, int(os.environ.get("DB_BACKUP_PG_DUMP_TIMEOUT_SEC") or 600)),
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip() or f"código {result.returncode}"
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        raise RuntimeError(f"pg_dump falló: {err[:500]}")


def run_database_backup(app: Any, *, force: bool = False) -> dict[str, Any]:
    """
    Ejecuta un respaldo si corresponde (o siempre con force=True).

    No toca la BD en uso: escribe un archivo aparte. Los usuarios siguen viendo
    la misma información en la app.
    """
    if not app.config.get("DB_BACKUP_ENABLED", True) and not force:
        return {"ok": False, "skipped": True, "message": "Respaldos desactivados (DB_BACKUP_ENABLED)."}

    if not force and not is_backup_due(app):
        meta = load_last_backup_meta(app) or {}
        return {
            "ok": True,
            "skipped": True,
            "message": "Aún no corresponde un nuevo respaldo diario.",
            "last": meta,
        }

    uri = database_uri(app)
    if not uri:
        out = {"ok": False, "message": "No hay SQLALCHEMY_DATABASE_URI configurada."}
        save_last_backup_meta(app, {**out, "finished_at_iso": _now_utc().strftime(_ISO_FMT)})
        return out

    if uri.lower().startswith("sqlite:") and ":memory:" in uri.lower():
        return {
            "ok": False,
            "skipped": True,
            "message": "SQLite en memoria no admite respaldo a disco.",
        }

    stamp = _now_utc().astimezone().strftime("%Y%m%d_%H%M%S")
    directory = backup_dir(app)
    engine = "unknown"
    dest: Path

    started = _now_utc()
    try:
        sqlite_path = sqlite_file_from_uri(uri)
        if sqlite_path is not None:
            engine = "sqlite"
            if not sqlite_path.is_file():
                raise FileNotFoundError(f"No existe el archivo SQLite: {sqlite_path}")
            dest = directory / f"qdv_backup_{stamp}.db"
            _backup_sqlite(sqlite_path, dest)
        elif "postgresql" in uri.lower() or uri.lower().startswith("postgres"):
            engine = "postgresql"
            dest = directory / f"qdv_backup_{stamp}.dump"
            _backup_postgres(uri, dest)
        else:
            raise RuntimeError(f"Motor de BD no soportado para respaldo automático: {uri.split(':', 1)[0]}")

        size = dest.stat().st_size if dest.is_file() else 0
        keep = max(1, int(app.config.get("DB_BACKUP_KEEP") or 8))
        _prune_old_backups(directory, keep)

        finished = _now_utc()
        meta = {
            "ok": True,
            "engine": engine,
            "filename": dest.name,
            "path": str(dest.resolve()),
            "size_bytes": size,
            "started_at_iso": started.strftime(_ISO_FMT),
            "finished_at_iso": finished.strftime(_ISO_FMT),
            "message": "Respaldo completado.",
        }
        save_last_backup_meta(app, meta)
        log.info(
            "Respaldo de BD listo (%s): %s (%s bytes)",
            engine,
            dest.name,
            size,
        )
        return meta
    except Exception as exc:
        log.exception("Fallo al respaldar la base de datos")
        meta = {
            "ok": False,
            "engine": engine,
            "finished_at_iso": _now_utc().strftime(_ISO_FMT),
            "message": str(exc)[:500],
        }
        # Conservar último éxito si existía
        prev = load_last_backup_meta(app)
        if prev and prev.get("ok") is True:
            meta["last_ok"] = {
                "finished_at_iso": prev.get("finished_at_iso"),
                "filename": prev.get("filename"),
                "path": prev.get("path"),
            }
        save_last_backup_meta(app, meta)
        return meta


def db_backup_context(app: Any | None = None) -> dict[str, Any]:
    """Contexto para el pie del menú lateral (último respaldo)."""
    from flask import current_app

    flask_app = app or current_app
    if not flask_app.config.get("DB_BACKUP_ENABLED", True):
        return {"db_backup_status": None}

    meta = load_last_backup_meta(flask_app)
    if not meta:
        return {
            "db_backup_status": {
                "ok": None,
                "label": "sin respaldo",
                "title": "Aún no hay un respaldo diario registrado. Se creará automáticamente.",
                "display": "",
            }
        }

    # Preferir último éxito si el más reciente falló
    if meta.get("ok") is not True and isinstance(meta.get("last_ok"), dict):
        ok_meta = meta["last_ok"]
        failed_msg = meta.get("message") or "El último intento falló"
        dt = _parse_iso(ok_meta.get("finished_at_iso"))
        short = _format_short(dt) or "—"
        full = _format_display(dt)
        return {
            "db_backup_status": {
                "ok": True,
                "label": short,
                "title": f"Último respaldo OK: {full or short}. Aviso: {failed_msg}",
                "display": full,
                "filename": ok_meta.get("filename") or "",
            }
        }

    dt = _parse_iso(meta.get("finished_at_iso") or meta.get("created_at_iso"))
    short = _format_short(dt) or "—"
    full = _format_display(dt)
    ok = meta.get("ok") is True
    if ok:
        title = f"Último respaldo: {full or short}"
        if meta.get("filename"):
            title += f" · {meta['filename']}"
    else:
        title = meta.get("message") or "El último intento de respaldo falló"
        short = "error"
    return {
        "db_backup_status": {
            "ok": ok,
            "label": short,
            "title": title,
            "display": full,
            "filename": meta.get("filename") or "",
        }
    }
