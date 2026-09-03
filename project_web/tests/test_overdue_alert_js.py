from __future__ import annotations

from pathlib import Path


def test_overdue_alert_js_respects_local_timer_ok():
    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "overdue_alert.js").read_text(
        encoding="utf-8"
    )
    assert "localOkKeys" in js
    assert "fromLocal" in js
    assert "Registrá ese análisis para apagar el aviso." in js
    # No mezclar Análisis 8 hs dentro del mensaje de Reactor.
    assert "si está «En tiempo», no apaga este aviso" not in js
    assert "Análisis 8 hs es otro cronómetro" not in js


def test_plant_stop_js_resolve_marks_local_ok():
    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "plant_stop.js").read_text(
        encoding="utf-8"
    )
    assert "resolve(key, { fromLocal: true })" in js
