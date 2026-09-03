from __future__ import annotations

from unittest.mock import patch

from app.services import plant_stop_service as ps
from app.services.timer_overdue_service import _status, list_timer_statuses


def test_status_overdue_at_zero_remaining():
    with patch.object(ps, "compute_remaining_seconds", return_value=0):
        s = _status(
            key="salmuera_e3",
            label="Electrolizador 3",
            last_iso="2026-09-03T10:00:00",
            interval_sec=7200,
            fecha="2026-09-03",
            paused=False,
        )
    assert s["overdue"] is True


def test_status_not_overdue_without_last_record():
    with patch.object(ps, "compute_remaining_seconds", return_value=0):
        s = _status(
            key="salmuera_e3",
            label="Electrolizador 3",
            last_iso=None,
            interval_sec=7200,
            fecha="2026-09-03",
            paused=False,
        )
    assert s["overdue"] is False


def test_status_not_overdue_when_paused():
    with patch.object(ps, "compute_remaining_seconds", return_value=-30):
        s = _status(
            key="salmuera_e3",
            label="Electrolizador 3",
            last_iso="2026-09-03T10:00:00",
            interval_sec=7200,
            fecha="2026-09-03",
            paused=True,
        )
    assert s["overdue"] is False


def test_list_timer_statuses_includes_overdue(app, monkeypatch):
    monkeypatch.setattr(
        "app.services.timer_overdue_service.last_salmuera_created_at_iso_for_electrolizador",
        lambda eid: "2026-09-03T10:00:00" if int(eid) == 3 else None,
    )
    monkeypatch.setattr("app.services.timer_overdue_service.last_reactor_created_at_iso", lambda: None)
    monkeypatch.setattr("app.services.timer_overdue_service.last_agua_created_at_iso", lambda: None)
    monkeypatch.setattr(
        "app.services.timer_overdue_service.filtro_svc.last_filtro_created_at_iso", lambda: None
    )
    monkeypatch.setattr("app.services.timer_overdue_service.a8_svc.latest_row", lambda: None)
    monkeypatch.setattr("app.services.timer_overdue_service.ps.today_operacion_iso", lambda: "2026-09-03")
    monkeypatch.setattr("app.services.timer_overdue_service.ps.get_active_stop", lambda _k: None)

    def _rem(last_iso, interval_sec, circuit_key, fecha_iso=None):
        if circuit_key == "salmuera_e3":
            return -5
        return int(interval_sec)

    monkeypatch.setattr("app.services.timer_overdue_service.ps.compute_remaining_seconds", _rem)

    with app.app_context():
        data = list_timer_statuses()
    assert data["ok"] is True
    keys = [t["key"] for t in data["overdue"]]
    assert "salmuera_e3" in keys
    assert "salmuera_e2" not in keys


def test_cronometros_estado_endpoint(auth_client):
    r = auth_client.get("/produccion/cronometros/estado")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert "timers" in payload
    assert "overdue" in payload
