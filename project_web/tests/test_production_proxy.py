from __future__ import annotations


def test_healthz_with_production_https_proxy_normalizer(monkeypatch):
    """Regresión: before_request usaba `request` sin importar → 500 en Render."""
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "pytest-production-secret-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SKIP_SEED_DATA", "1")

    from app import create_app
    from app.extensions import db

    application = create_app()
    with application.app_context():
        db.create_all()
        client = application.test_client()
        r = client.get("/healthz", headers={"X-Forwarded-Proto": "https"})
        assert r.status_code == 200
        assert r.get_data(as_text=True) == "ok"

        login = client.get("/login", headers={"X-Forwarded-Proto": "https"})
        assert login.status_code == 200
