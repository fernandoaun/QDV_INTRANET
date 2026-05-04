from __future__ import annotations

import re

import pytest


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/dashboard", "/dashboard"),
        ("//evil.com/x", None),
        ("https://evil.com", None),
        ("\\\\server\\share", None),
        ("javascript:alert(1)", None),
        ("/salmuera?q=1", "/salmuera"),
    ],
)
def test_safe_internal_redirect(raw, expected):
    from app.security_http import safe_internal_redirect_target

    assert safe_internal_redirect_target(raw) == expected


def test_health_endpoint_ok(app):
    c = app.test_client()
    r = c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.is_json


def test_login_audit_row_on_failure(app, client):
    """Fallo de login registra auditoría en tabla security_audit_logs."""
    client.get("/login")
    client.post(
        "/login",
        data={"username": "nope", "password": "wrong", "csrf_token": _csrf_any(client)},
    )

    from sqlalchemy import select

    from app.extensions import db
    from app.models import SecurityAuditLog

    with app.app_context():
        n = db.session.scalar(select(SecurityAuditLog.id).where(SecurityAuditLog.action == "login_fail").limit(1))
    assert n is not None


def _csrf_any(client):
    lg = client.get("/login")
    html = lg.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    return m.group(1)
