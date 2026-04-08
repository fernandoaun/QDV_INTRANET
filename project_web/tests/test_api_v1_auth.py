from __future__ import annotations


def test_shift_status_authenticated(auth_client):
    r = auth_client.get("/api/v1/shift/status")
    assert r.status_code == 200
    data = r.get_json()
    assert "user_id" in data
    assert data["participates_operational_shift"] is False


def test_dashboard_snapshot_authenticated_admin(auth_client):
    r = auth_client.get("/api/v1/dashboard/snapshot")
    assert r.status_code == 200
    data = r.get_json()
    assert "alertas_stock" in data
    assert isinstance(data["alertas_stock"], list)


def test_entregas_forbidden_for_mantenimiento(mant_client):
    assert mant_client.get("/api/v1/entregas").status_code == 403


def test_stock_existencias_ok_for_mantenimiento(mant_client):
    r = mant_client.get("/api/v1/stock/existencias?categoria=todas")
    assert r.status_code == 200
    data = r.get_json()
    assert "items" in data
