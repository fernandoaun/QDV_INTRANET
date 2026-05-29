from __future__ import annotations

from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app.constants import ANALYSIS_INTERVAL_SECONDS
from app.extensions import db
from app.models import PlantStopEvent, User
from app.services import plant_stop_service as ps
from app.user_roles import ROLE_OPERACIONES


def test_start_and_end_plant_stop_freezes_timer_context(app):
    with app.app_context():
        u = User(
            username="pytest_plant_stop",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add(u)
        db.session.commit()

        anchor = "2026-05-29T10:00:00"
        with patch.object(ps, "now_local_iso", return_value="2026-05-29T11:00:00"):
            ev = ps.start_plant_stop(
                app,
                circuit_key=ps.CIRCUIT_SALMUERA_E2,
                user=u,
                operador="Operador Test",
                last_created_iso=anchor,
                interval_sec=int(ANALYSIS_INTERVAL_SECONDS),
            )
        assert ev.ended_at_iso is None
        assert ev.frozen_remaining_sec is not None
        assert ev.frozen_remaining_sec >= 0

        state = ps.timer_ui_state(
            ps.CIRCUIT_SALMUERA_E2,
            anchor,
            int(ANALYSIS_INTERVAL_SECONDS),
            fecha_iso="2026-05-29",
        )
        assert state["active"] is True
        assert state["frozen_remaining_sec"] == ev.frozen_remaining_sec

        with patch.object(ps, "now_local_iso", return_value="2026-05-29T14:00:00"):
            ended = ps.end_plant_stop(ps.CIRCUIT_SALMUERA_E2)
        assert ended.ended_at_iso is not None
        assert ps.get_active_stop(ps.CIRCUIT_SALMUERA_E2) is None

        pause_sec = ps.pause_seconds_after_anchor(anchor, ps.CIRCUIT_SALMUERA_E2)
        assert pause_sec == 3 * 3600


def test_reactor_stop_sets_analisis8_frozen(app):
    with app.app_context():
        from app.models import SalmueraAnalisis8hs

        u = User(
            username="pytest_plant_stop_8h",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add(u)
        db.session.add(
            SalmueraAnalisis8hs(
                fecha="2026-05-29",
                hora="08:00",
                fecha_hora_iso="2026-05-29T08:00:00",
                turno="Mañana",
                operador="Op",
                dureza_salmuera=1.0,
                cloro_libre_salmuera=2.0,
                created_at_iso="2026-05-29T08:00:00",
            )
        )
        db.session.commit()

        with patch.object(ps, "now_local_iso", return_value="2026-05-29T10:00:00"):
            ev = ps.start_plant_stop(
                app,
                circuit_key=ps.CIRCUIT_REACTOR,
                user=u,
                operador="Op",
                last_created_iso="2026-05-29T09:00:00",
                interval_sec=int(ANALYSIS_INTERVAL_SECONDS),
                observaciones="Mantenimiento programado",
            )
        assert ev.frozen_remaining_sec_analisis8 is not None
        assert (ev.observaciones or "").startswith("Mantenimiento")

        overlay = ps.analisis8_plant_stop_overlay(
            last_fecha_hora_iso="2026-05-29T08:00:00",
            interval_sec=8 * 3600,
            fecha_iso="2026-05-29",
        )
        assert overlay["active"] is True
        assert overlay["frozen_remaining_sec"] == ev.frozen_remaining_sec_analisis8


def test_analisis8_overlay_ignores_stop_on_historical_fecha(app):
    with app.app_context():
        u = User(
            username="pytest_plant_stop_hist",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add(u)
        db.session.commit()

        with patch.object(ps, "now_local_iso", return_value="2026-05-29T11:00:00"), patch.object(
            ps, "today_operacion_iso", return_value="2026-05-29"
        ):
            ps.start_plant_stop(
                app,
                circuit_key=ps.CIRCUIT_REACTOR,
                user=u,
                operador="Op",
                last_created_iso="2026-05-29T09:00:00",
                interval_sec=int(ANALYSIS_INTERVAL_SECONDS),
            )

        overlay_hoy = ps.analisis8_plant_stop_overlay(
            last_fecha_hora_iso="2026-05-28T08:00:00",
            interval_sec=8 * 3600,
            fecha_iso="2026-05-29",
        )
        overlay_ayer = ps.analisis8_plant_stop_overlay(
            last_fecha_hora_iso="2026-05-28T08:00:00",
            interval_sec=8 * 3600,
            fecha_iso="2026-05-28",
        )
        assert overlay_hoy["active"] is True
        assert overlay_ayer["active"] is False

        state_ayer = ps.timer_ui_state(
            ps.CIRCUIT_REACTOR,
            "2026-05-28T10:00:00",
            int(ANALYSIS_INTERVAL_SECONDS),
            fecha_iso="2026-05-28",
        )
        assert state_ayer["active"] is False


def test_list_stops_in_interval(app):
    with app.app_context():
        db.session.add(
            PlantStopEvent(
                circuit_key=ps.CIRCUIT_AGUA,
                started_at_iso="2026-05-29T08:00:00",
                ended_at_iso="2026-05-29T09:30:00",
                operador="A",
                created_at_iso="2026-05-29T08:00:00",
            )
        )
        db.session.commit()
        rows = ps.list_stops_in_interval("2026-05-29T07:00:00", "2026-05-29T10:00:00")
        assert len(rows) == 1
        assert rows[0]["circuit_label"] == ps.CIRCUIT_LABELS[ps.CIRCUIT_AGUA]
