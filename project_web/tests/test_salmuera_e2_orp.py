from __future__ import annotations

import re


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _valid_salmuera_payload(csrf_token: str, *, electrolizador: str, orp: str) -> dict[str, str]:
    return {
        "csrf_token": csrf_token,
        "action": "guardar",
        "electrolizador": electrolizador,
        "cantidad_celdas": "2",
        "voltajes": "3.0, 3.1",
        "amperaje": "120",
        "caudal_agua_l_h": "10",
        "caudal_salmuera_l_h": "20",
        "hipo_conc": "1.2",
        "hipo_exceso_soda": "2.3",
        "sal_temp": "24.5",
        "sal_conc": "260",
        "sal_ph": "4.8",
        "soda_conc": "30",
        "declor_ph": "1.2",
        "orp": orp,
    }


def test_salmuera_orp_only_shows_and_saves_for_electrolizador_2(app, auth_client):
    from app.extensions import db
    from app.models import SalmueraRegistro

    page = auth_client.get("/produccion/salmuera?fecha=2026-04-30")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    panel_2 = html.split("Electrolizador 2", 1)[1].split("Electrolizador 3", 1)[0]
    panel_3 = html.split("Electrolizador 3", 1)[1]
    assert "ORP (mV)" in panel_2
    assert "ORP (mV)" not in panel_3

    e2 = auth_client.post(
        "/produccion/salmuera?fecha=2026-04-30",
        data=_valid_salmuera_payload(_csrf(html), electrolizador="2", orp="-123,5"),
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )
    assert e2.status_code == 200
    assert e2.get_json()["registro"]["orp"] == -123.5

    with app.app_context():
        row = db.session.query(SalmueraRegistro).filter_by(electrolizador=2).one()
        assert row.orp == -123.5


def test_salmuera_orp_is_ignored_for_other_electrolizadores(app, auth_client):
    from app.extensions import db
    from app.models import SalmueraRegistro

    page = auth_client.get("/produccion/salmuera?fecha=2026-04-30")
    assert page.status_code == 200
    resp = auth_client.post(
        "/produccion/salmuera?fecha=2026-04-30",
        data=_valid_salmuera_payload(_csrf(page.get_data(as_text=True)), electrolizador="3", orp="abc"),
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["registro"]["orp"] is None

    with app.app_context():
        row = db.session.query(SalmueraRegistro).filter_by(electrolizador=3).one()
        assert row.orp is None


def test_salmuera_orp_rejects_non_numeric_for_electrolizador_2(auth_client):
    page = auth_client.get("/produccion/salmuera?fecha=2026-04-30")
    assert page.status_code == 200
    resp = auth_client.post(
        "/produccion/salmuera?fecha=2026-04-30",
        data=_valid_salmuera_payload(_csrf(page.get_data(as_text=True)), electrolizador="2", orp="abc"),
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )
    assert resp.status_code == 400
    assert "ORP (mV) debe ser numérico" in resp.get_json()["error"]
