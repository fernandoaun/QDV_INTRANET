from __future__ import annotations

from datetime import datetime, timedelta

import pytest


def _parada(circuit, ini, fin=None):
    from app.extensions import db
    from app.models import PlantStopEvent

    db.session.add(PlantStopEvent(circuit_key=circuit, started_at_iso=ini, ended_at_iso=fin, operador="op", created_at_iso=ini))
    db.session.commit()


def test_estimacion_por_electrolizador_descuenta_paradas(app):
    from app.services import produccion_estimada_service as pe

    with app.app_context():
        assert pe.electrolizadores() == [2, 3]
        # 4 h sin paradas: 2 × 4 h × 1500/8 = 1500 L.
        r = pe.estimar("2026-10-01T08:00:00", "2026-10-01T12:00:00")
        assert r["litros"] == pytest.approx(1500.0)
        # E2 parado 09:00–10:30 (1,5 h) y E3 con parada abierta desde las 11:00.
        _parada("salmuera_e2", "2026-10-01T09:00:00", "2026-10-01T10:30:00")
        _parada("salmuera_e3", "2026-10-01T11:00:00")
        # Una parada de otro circuito no frena a los electrolizadores.
        _parada("reactor", "2026-10-01T08:00:00", "2026-10-01T12:00:00")
        r = pe.estimar("2026-10-01T08:00:00", "2026-10-01T12:00:00")
        assert r["detalle"][2]["horas_en_marcha"] == pytest.approx(2.5)
        assert r["detalle"][3]["horas_en_marcha"] == pytest.approx(3.0)
        assert r["litros"] == pytest.approx((2.5 + 3.0) * 187.5)


def test_tope_de_24_horas_y_configuracion(app):
    from werkzeug.datastructures import MultiDict

    from app.extensions import db
    from app.services import produccion_estimada_service as pe

    with app.app_context():
        r = pe.estimar("2026-10-01T00:00:00", "2026-10-03T00:00:00")
        assert r["litros"] == pytest.approx(2 * 24 * 187.5)
        assert pe.guardar_config(MultiDict({"horas_turno": "8", "margen_carga_pct": "150", "litros_e2": "1500", "litros_e3": "x"}), None)
        errs = pe.guardar_config(MultiDict({"horas_turno": "8", "margen_carga_pct": "80", "litros_e2": "1200", "litros_e3": "1600"}), None)
        assert errs == []
        db.session.commit()
        cfg = pe.config()
        assert cfg["margen_carga_pct"] == 80 and cfg["litros_turno"] == {2: 1200, 3: 1600}


def test_camion_de_4000_con_cierre_de_3000(app):
    """El caso real: el cierre dejó 3.000 L, pasaron 4 h de producción y viene un camión de 4.000 L."""
    from app.extensions import db
    from app.models import ShiftHandover, ShiftSession, User
    from app.services import operational_informed_stock as st
    from app.services import shift_handover_service as sh

    with app.app_context():
        ahora = datetime.fromisoformat(sh.now_local_iso())
        t0 = (ahora - timedelta(hours=4)).isoformat(timespec="seconds")
        u = User(username="pytest_estimada", password_hash="x", is_admin=False, activo=True, rol="operaciones")
        db.session.add(u)
        db.session.flush()
        prev = ShiftSession(user_id=u.id, effective_role="operaciones", started_at_iso="2026-01-01T00:00:00",
                            ended_at_iso=t0, status="closed", created_at_iso=t0, updated_at_iso=t0)
        db.session.add(prev)
        db.session.flush()
        db.session.add(ShiftHandover(shift_session_id=prev.id, outgoing_user_id=u.id, shift_started_at_iso="2026-01-01T00:00:00",
                                     handed_over_at_iso=t0, received_at_iso=t0, hypochlorite_stock_liters=3000.0,
                                     status=sh.HANDOVER_RECEIVED, created_at_iso=t0, updated_at_iso=t0))
        db.session.add(ShiftSession(user_id=u.id, effective_role="operaciones", started_at_iso=t0, status="open",
                                    created_at_iso=t0, updated_at_iso=t0))
        db.session.commit()

        c = st.get_stock_components()
        assert c["produccion_estimada"] == pytest.approx(1500.0, abs=2)
        assert st.get_instant_stock() == pytest.approx(4500.0, abs=2)
        # Margen 90 %: 3000 + 0,9 × 1500 = 4350 disponibles para cargar.
        assert st.get_carga_available() == pytest.approx(4350.0, abs=2)
        st.raise_if_carga_qty_exceeds_instant(4000)
        with pytest.raises(ValueError, match="Disponible para carga"):
            st.raise_if_carga_qty_exceeds_instant(4400)
        assert "producción estimada" in st.header_operational_indicators_dict()["stock_panel_subnote"]


def test_pantalla_de_configuracion(auth_client):
    html = auth_client.get("/admin/produccion-estimada").get_data(as_text=True)
    assert "Producción estimada de hipoclorito" in html and "Electrolizador 2" in html and "Margen para cargar" in html
    r = auth_client.post("/admin/produccion-estimada", data={"horas_turno": "8", "margen_carga_pct": "90", "litros_e2": "1500", "litros_e3": "1500"})
    assert r.status_code in (302, 303)


def test_turno_entregado_sin_recepcionar_parte_de_lo_declarado(app):
    """Caso real del 01/10: cierre recepcionado 3.000 L, turno entregado (sin recepcionar) declarando 1.000 L.
    El stock tiene que partir de los 1.000 L medidos, no volver a sumar la producción de ese turno."""
    from app.extensions import db
    from app.models import Entrega, ShiftHandover, ShiftSession, User
    from app.services import operational_informed_stock as st
    from app.services import shift_handover_service as sh

    with app.app_context():
        ahora = datetime.fromisoformat(sh.now_local_iso())
        iso = lambda h: (ahora - timedelta(hours=h)).isoformat(timespec="seconds")  # noqa: E731
        u = User(username="pytest_pendiente", password_hash="x", is_admin=False, activo=True, rol="operaciones")
        db.session.add(u)
        db.session.flush()
        s1 = ShiftSession(user_id=u.id, effective_role="operaciones", started_at_iso=iso(16), ended_at_iso=iso(8),
                          status="closed", created_at_iso=iso(16), updated_at_iso=iso(8))
        s2 = ShiftSession(user_id=u.id, effective_role="operaciones", started_at_iso=iso(7), ended_at_iso=iso(0.5),
                          status="closed", created_at_iso=iso(7), updated_at_iso=iso(0.5))
        db.session.add_all([s1, s2])
        db.session.flush()
        db.session.add(ShiftHandover(shift_session_id=s1.id, outgoing_user_id=u.id, shift_started_at_iso=iso(16),
                                     handed_over_at_iso=iso(8), received_at_iso=iso(7), hypochlorite_stock_liters=3000.0,
                                     status=sh.HANDOVER_RECEIVED, created_at_iso=iso(8), updated_at_iso=iso(7)))
        db.session.add(ShiftHandover(shift_session_id=s2.id, outgoing_user_id=u.id, shift_started_at_iso=iso(7),
                                     handed_over_at_iso=iso(0.5), hypochlorite_stock_liters=1000.0,
                                     status=sh.HANDOVER_PENDING, created_at_iso=iso(0.5), updated_at_iso=iso(0.5)))
        # Camión cargado durante el turno ya entregado: ya está reflejado en los 1.000 L declarados.
        db.session.add(Entrega(cliente="C", lugar_entrega="P", producto="Hipoclorito", cantidad=3500.0, unidad="L",
                               fecha_prevista=iso(3)[:10], estado="cargada", created_at_iso=iso(3),
                               updated_at_iso=iso(3), cargada_at_iso=iso(3)))
        db.session.commit()

        c = st.get_stock_components()
        assert c["s0"] == 1000.0 and c["cargas"] == 0.0
        # Media hora desde la entrega con los dos electrolizadores: 0,5 h × 375 L/h.
        assert c["produccion_estimada"] == pytest.approx(187.5, abs=2)
        assert st.get_instant_stock() == pytest.approx(1187.5, abs=2)
