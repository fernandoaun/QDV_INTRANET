from __future__ import annotations

from pathlib import Path


def test_overdue_alert_js_explains_reactor_vs_analisis8():
    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "overdue_alert.js").read_text(
        encoding="utf-8"
    )
    assert "Nuevo registro" in js
    assert "Análisis 8 hs es otro cronómetro" in js
    assert "scrollToOverdueTarget" in js
    assert "reactorMainForm" in js
