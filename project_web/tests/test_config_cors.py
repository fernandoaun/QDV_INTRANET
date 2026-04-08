from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://a.com,http://b.dev", ["https://a.com", "http://b.dev"]),
        (" https://x.test , ", ["https://x.test"]),
        ("", []),
    ],
)
def test_cors_origins_env_parsed(monkeypatch, raw, expected):
    monkeypatch.setenv("FLASK_ENV", "testing")
    if raw:
        monkeypatch.setenv("CORS_ORIGINS", raw)
    else:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    from config import get_config_dict

    base = Path(__file__).resolve().parent.parent
    cfg = get_config_dict(base)
    assert cfg["CORS_ORIGINS"] == expected
