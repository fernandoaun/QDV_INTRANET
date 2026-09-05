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
    assert "localOkKeys" in js
    assert "refreshModalText" in js
    # Meta null no debe mostrarse como 00:00:00 / sin registro engañoso.
    assert 'return "—"' in js
    # El poll no debe pintar timerText: eso hacía alternar Atrasado / En tiempo.
    assert "syncDomTimerFromServer" not in js
    assert "Vencido (servidor)" not in js


def test_plant_stop_js_resolve_marks_from_local():
    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "plant_stop.js").read_text(
        encoding="utf-8"
    )
    assert "resolve(key, { fromLocal: true })" in js
    assert "applyServerSnapshot" in js
    assert "Nunca borrar un ancla conocida" in js
    # El tick local debe mandar último + remaining para el modal.
    assert "last_created_at_iso: lastCreatedIso" in js
    assert "remaining: diffSec" in js


def test_reactor_analisis8_notify_includes_meta():
    html = (
        Path(__file__).resolve().parents[1] / "app" / "templates" / "produccion" / "reactor.html"
    ).read_text(encoding="utf-8")
    assert "analisis8AnchorIso" in html
    assert "notifyAnalisis8(true, diffSec)" in html
    assert 'QdvOverdueAlert.report("analisis_8hs"' in html
