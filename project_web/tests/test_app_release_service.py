"""Tests del registro de versiones de la intranet (RELEASES.json)."""
from __future__ import annotations

import json


def test_app_release_service_loads_changelog(tmp_path, monkeypatch):
    from app.services import app_release_service as rel_svc

    releases = tmp_path / "RELEASES.json"
    releases.write_text(
        json.dumps(
            {
                "version": "1.2.3",
                "changelog": [
                    {"version": "1.2.3", "date": "2026-06-30", "description": "Organigrama interactivo."},
                    {"version": "1.2.2", "date": "2026-06-15", "description": "Correcciones menores."},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rel_svc, "_releases_path", lambda: releases)
    rel_svc._load_releases_cached.cache_clear()

    ctx = rel_svc.app_release_context()
    assert ctx["app_release_version"] == "1.2.3"
    assert len(ctx["app_release_changelog"]) == 2
    assert ctx["app_release_changelog"][0]["version"] == "1.2.3"
    assert ctx["app_release_changelog"][0]["date_display"] == "30/06/2026"
    assert "Organigrama" in ctx["app_release_changelog"][0]["description"]
