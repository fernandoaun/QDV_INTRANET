from __future__ import annotations

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User
from app.user_roles import ROLE_SOLO_LECTURA_TOTAL


def test_create_openclaw_bot_prints_user_id(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-openclaw-bot", "--password", "bot-secret-ok"])
    assert result.exit_code == 0, result.output
    assert "API_BEARER_USER_ID=" in result.output
    with app.app_context():
        u = db.session.query(User).filter_by(username="openclaw").one()
        assert u.rol == ROLE_SOLO_LECTURA_TOTAL
        assert u.is_admin is False
        assert u.activo is True
        assert f"API_BEARER_USER_ID={u.id}" in result.output


def test_create_openclaw_bot_is_idempotent(app):
    runner = app.test_cli_runner()
    first = runner.invoke(args=["create-openclaw-bot", "--password", "bot-secret-ok"])
    assert first.exit_code == 0, first.output
    second = runner.invoke(args=["create-openclaw-bot"])
    assert second.exit_code == 0, second.output
    assert "ya existe" in second.output
    with app.app_context():
        n = db.session.query(User).filter_by(username="openclaw").count()
        assert n == 1


def test_api_bearer_openclaw_bot_can_read_dashboard(app, client):
    with app.app_context():
        u = User(
            username="openclaw_bearer",
            password_hash=generate_password_hash("unused"),
            is_admin=False,
            activo=True,
            rol=ROLE_SOLO_LECTURA_TOTAL,
        )
        db.session.add(u)
        db.session.commit()
        uid = u.id

    app.config["API_BEARER_TOKEN"] = "openclaw-test-token-32chars-min"
    app.config["API_BEARER_USER_ID"] = uid
    r = client.get(
        "/api/v1/dashboard/snapshot",
        headers={"Authorization": "Bearer openclaw-test-token-32chars-min"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "alertas_stock" in data

    bad = client.get(
        "/api/v1/dashboard/snapshot",
        headers={"Authorization": "Bearer token-incorrecto"},
    )
    assert bad.status_code == 401
