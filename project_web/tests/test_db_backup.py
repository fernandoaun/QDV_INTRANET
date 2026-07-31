"""Tests del respaldo diario de base de datos."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def test_sqlite_online_backup_preserves_data_and_is_due(tmp_path, monkeypatch):
    from app.services import db_backup_service as svc

    src = tmp_path / "live.db"
    con = sqlite3.connect(str(src))
    con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO items (name) VALUES ('alfa'), ('beta')")
    con.commit()
    con.close()

    backup_root = tmp_path / "backups"
    monkeypatch.setenv("DB_BACKUP_DIR", str(backup_root))
    monkeypatch.setenv("DB_BACKUP_INTERVAL_DAYS", "7")
    monkeypatch.setenv("DB_BACKUP_KEEP", "3")
    monkeypatch.setenv("FLASK_ENV", "testing")

    from app import create_app

    app = create_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{src.as_posix()}"
    app.config["DB_BACKUP_DIR"] = str(backup_root)
    app.config["DB_BACKUP_ENABLED"] = True
    app.config["DB_BACKUP_INTERVAL_DAYS"] = 7
    app.config["DB_BACKUP_KEEP"] = 3

    with app.app_context():
        assert svc.is_backup_due(app) is True
        out = svc.run_database_backup(app, force=True)
        assert out["ok"] is True
        assert out["engine"] == "sqlite"
        dest = Path(out["path"])
        assert dest.is_file()
        assert dest.stat().st_size > 0

        # La BD en vivo sigue intacta (respaldo transparente)
        live = sqlite3.connect(str(src))
        rows = live.execute("SELECT name FROM items ORDER BY id").fetchall()
        live.close()
        assert rows == [("alfa",), ("beta",)]

        # El archivo de respaldo tiene los mismos datos
        bak = sqlite3.connect(str(dest))
        bak_rows = bak.execute("SELECT name FROM items ORDER BY id").fetchall()
        bak.close()
        assert bak_rows == [("alfa",), ("beta",)]

        assert svc.is_backup_due(app) is False

        ctx = svc.db_backup_context(app)
        status = ctx["db_backup_status"]
        assert status is not None
        assert status["ok"] is True
        assert "/" in status["label"]  # dd/mm/yyyy


def test_backup_not_due_within_interval(tmp_path, monkeypatch):
    from app.services import db_backup_service as svc

    src = tmp_path / "live.db"
    sqlite3.connect(str(src)).close()
    backup_root = tmp_path / "backups"

    from app import create_app

    app = create_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{src.as_posix()}"
    app.config["DB_BACKUP_DIR"] = str(backup_root)
    app.config["DB_BACKUP_ENABLED"] = True
    app.config["DB_BACKUP_INTERVAL_DAYS"] = 7

    with app.app_context():
        first = svc.run_database_backup(app, force=True)
        assert first["ok"] is True
        skipped = svc.run_database_backup(app, force=False)
        assert skipped.get("skipped") is True


def test_prune_keeps_only_n(tmp_path):
    from app.services.db_backup_service import _prune_old_backups

    d = tmp_path / "b"
    d.mkdir()
    files = []
    for i in range(5):
        p = d / f"qdv_backup_2026010{i+1}_120000.db"
        p.write_bytes(b"x" * (i + 1))
        files.append(p)
        # Ensure distinct mtimes
        ts = datetime(2026, 1, i + 1, tzinfo=timezone.utc).timestamp()
        import os

        os.utime(p, (ts, ts))

    _prune_old_backups(d, keep=2)
    remaining = sorted(d.glob("qdv_backup_*.db"))
    assert len(remaining) == 2
    assert remaining[0].name.endswith("04_120000.db") or remaining[-1].name.endswith("05_120000.db")


def test_memory_sqlite_skipped(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    from app import create_app
    from app.services import db_backup_service as svc

    app = create_app()
    with app.app_context():
        out = svc.run_database_backup(app, force=True)
        assert out.get("skipped") is True


def test_sidebar_shows_backup_pending(auth_client):
    r = auth_client.get("/dashboard", follow_redirects=True)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "app-backup-status" in html
    assert "pendiente" in html or "Backup" in html
