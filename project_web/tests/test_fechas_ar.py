from __future__ import annotations

from datetime import date, datetime

from app.utils.fechas import fecha_ar, fechas_ar_en_texto


def test_fecha_ar_tipos():
    assert fecha_ar(date(2026, 10, 7)) == "07/10/2026"
    assert fecha_ar(datetime(2026, 10, 7, 9, 5, 30)) == "07/10/2026 09:05"
    assert fecha_ar("2026-10-07") == "07/10/2026"
    assert fecha_ar("2026-10-07T13:29:09") == "07/10/2026 13:29"
    assert fecha_ar("2026-10-07T13:29:09", con_hora=False) == "07/10/2026"
    assert fecha_ar(None) == "" and fecha_ar("") == ""


def test_fechas_ar_en_texto_respeta_lo_que_no_es_fecha():
    assert fechas_ar_en_texto("Del 2026-10-01 al 2026-10-31.") == "Del 01/10/2026 al 31/10/2026."
    assert fechas_ar_en_texto("Inicio: 2026-09-30 13:29:09+00:00") == "Inicio: 30/09/2026 13:29"
    for intacto in ("lote L2026-10-07", "QDV-RG-PO-04_01", "26665-06-14", "2026-13-40", "12/10/2026"):
        assert fechas_ar_en_texto(intacto) == intacto


def test_base_incluye_conversion_de_fechas(client):
    html = client.get("/login").get_data(as_text=True)
    assert "js/fechas_ar.js" in html
