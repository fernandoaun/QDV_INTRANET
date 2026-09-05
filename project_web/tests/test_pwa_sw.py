from __future__ import annotations

from pathlib import Path


def test_service_worker_never_caches_cronometros_estado():
    sw = (Path(__file__).resolve().parents[1] / "app" / "static" / "pwa" / "sw.js").read_text(
        encoding="utf-8"
    )
    assert "qdv-pwa-v5" in sw
    assert "/produccion/cronometros/estado" in sw
    assert "isLiveDataRequest" in sw
    assert "networkOnly" in sw
    # No precachear "/" : una Inicio vieja en el celular dejaba el rojo pegado.
    assert '"/"' not in sw.split("var PRECACHE")[1].split("];")[0]
