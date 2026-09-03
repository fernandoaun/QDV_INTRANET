from __future__ import annotations

from pathlib import Path


def test_overdue_alert_js_persists_dismiss_and_shows_meta():
    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "overdue_alert.js").read_text(
        encoding="utf-8"
    )
    assert "qdvOverdueDismissedV2" in js
    assert "sessionStorage" in js
    assert "last_created_at_iso" in js
    assert "atraso" in js
    assert "applyServerSnapshot" in js
    assert "hasLastAnchor" in js
    # El poll no debe pintar timerText: eso hacía alternar Atrasado / En tiempo.
    assert "syncDomTimerFromServer" not in js
    assert "Vencido (servidor)" not in js
    # No bloquear el poll con localOk (eso hacía que al salir de salmuera/reactor volviera el modal).
    assert "localOkKeys" not in js


def test_plant_stop_js_resolve_marks_from_local():
    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "plant_stop.js").read_text(
        encoding="utf-8"
    )
    assert "resolve(key, { fromLocal: true })" in js
    assert "applyServerSnapshot" in js
    assert "Nunca borrar un ancla conocida" in js
