from __future__ import annotations


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "service": "qdv_web"}


def test_sync_meta_ok(client):
    r = client.get("/api/v1/sync/meta")
    assert r.status_code == 200
    data = r.get_json()
    assert data["api_version"] == 1
    assert "server_time_utc" in data


def test_shift_status_unauthorized(client):
    assert client.get("/api/v1/shift/status").status_code == 401


def test_entregas_unauthorized(client):
    assert client.get("/api/v1/entregas").status_code == 401


def test_stock_existencias_unauthorized(client):
    assert client.get("/api/v1/stock/existencias").status_code == 401


def test_dashboard_snapshot_unauthorized(client):
    assert client.get("/api/v1/dashboard/snapshot").status_code == 401


def test_openapi_json_available_in_testing(client, app):
    assert app.config.get("API_DOCS_REQUIRE_AUTH") is False
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    spec = r.get_json()
    assert spec["openapi"] == "3.0.3"
    assert "/api/v1/health" in spec["paths"]


def test_openapi_json_requires_auth_when_configured(client, app):
    app.config["API_DOCS_REQUIRE_AUTH"] = True
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 401
    assert r.get_json()["error"] == "unauthorized"


def test_api_docs_redirects_when_auth_required(client, app):
    app.config["API_DOCS_REQUIRE_AUTH"] = True
    r = client.get("/api/v1/docs", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("Location", "").startswith("/login")
