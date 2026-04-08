from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_cors_preflight_options_on_api_health_subprocess():
    """
    CORS en proceso limpio (evita estado global del blueprint en el worker de pytest).
    """
    code = """
import os
os.environ["FLASK_ENV"] = "testing"
os.environ["CORS_ORIGINS"] = "https://spa.example"
from app import create_app
app = create_app()
c = app.test_client()
r = c.open(
    "/api/v1/health",
    method="OPTIONS",
    headers={
        "Origin": "https://spa.example",
        "Access-Control-Request-Method": "GET",
    },
)
assert r.status_code in (200, 204), r.status_code
assert r.headers.get("Access-Control-Allow-Origin") == "https://spa.example"
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
