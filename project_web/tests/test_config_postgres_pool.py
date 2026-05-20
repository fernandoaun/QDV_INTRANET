from __future__ import annotations

from pathlib import Path

import pytest

_BASE = Path(__file__).resolve().parent.parent


def test_postgres_production_sets_engine_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com:5432/app")
    from config import get_config_dict

    cfg = get_config_dict(_BASE)
    opts = cfg["SQLALCHEMY_ENGINE_OPTIONS"]
    assert opts["pool_pre_ping"] is True
    assert opts["pool_recycle"] == 280
    assert opts["connect_args"] == {"connect_timeout": 15}


def test_postgres_pool_pre_ping_can_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com:5432/app")
    monkeypatch.setenv("SQLALCHEMY_POOL_PRE_PING", "false")
    from config import get_config_dict

    cfg = get_config_dict(_BASE)
    opts = cfg["SQLALCHEMY_ENGINE_OPTIONS"]
    assert "pool_pre_ping" not in opts
    assert opts["pool_recycle"] == 280


def test_sqlite_testing_has_no_postgres_engine_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from config import get_config_dict

    cfg = get_config_dict(_BASE)
    assert "SQLALCHEMY_ENGINE_OPTIONS" not in cfg
