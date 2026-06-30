"""Tests del dashboard de operadores (atrasos y producción mensual)."""
from __future__ import annotations


def test_ranking_atrasos_hipoclorito_por_motivo(app):
    from app.extensions import db
    from app.models import SalmueraRegistro
    from app.services.operador_dashboard_service import ranking_atrasos_analisis

    with app.app_context():
        db.session.add(
            SalmueraRegistro(
                fecha_iso="2026-06-10",
                hora_hm="08:00",
                electrolizador=2,
                cantidad_celdas=10,
                turno="M",
                voltajes_json="[]",
                voltaje_total=100.0,
                amperaje=50.0,
                caudal_agua_l_h=10.0,
                caudal_salmuera_l_h=10.0,
                hipo_conc=1.0,
                hipo_exceso_soda=0.1,
                sal_temp=25.0,
                sal_conc=1.0,
                sal_ph=7.0,
                soda_conc=1.0,
                declor_ph=7.0,
                operador="op_uno",
                created_at_iso="2026-06-10T08:00:00",
            )
        )
        db.session.add(
            SalmueraRegistro(
                fecha_iso="2026-06-10",
                hora_hm="11:00",
                electrolizador=2,
                cantidad_celdas=10,
                turno="M",
                voltajes_json="[]",
                voltaje_total=100.0,
                amperaje=50.0,
                caudal_agua_l_h=10.0,
                caudal_salmuera_l_h=10.0,
                hipo_conc=1.0,
                hipo_exceso_soda=0.1,
                sal_temp=25.0,
                sal_conc=1.0,
                sal_ph=7.0,
                soda_conc=1.0,
                declor_ph=7.0,
                operador="op_uno",
                atraso_motivo="Demora en laboratorio",
                created_at_iso="2026-06-10T11:00:00",
            )
        )
        db.session.commit()

        ranking = ranking_atrasos_analisis(
            desde_iso="2026-06-01T00:00:00",
            hasta_iso_exclusive="2026-07-01T00:00:00",
        )
        assert len(ranking) == 1
        assert ranking[0]["operador"] == "op_uno"
        assert ranking[0]["total_atrasos"] == 1
        assert ranking[0]["total_segundos_atraso"] == 3600
        assert ranking[0]["tiempo_atraso_total_display"] == "1 h"
        assert any(d["tipo"] == "hipoclorito_e2" for d in ranking[0]["desglose"])


def test_format_atraso_duration():
    from app.services.operador_dashboard_service import format_atraso_duration

    assert format_atraso_duration(0) == "0 s"
    assert format_atraso_duration(45) == "45 s"
    assert format_atraso_duration(90) == "1 min 30 s"
    assert format_atraso_duration(3600) == "1 h"
    assert format_atraso_duration(5400) == "1 h 30 min"


def test_produccion_por_operador_mes(app):
    from app.extensions import db
    from app.models import ShiftHandover, ShiftSession, User
    from app.services import shift_handover_service as sh
    from app.services.operador_dashboard_service import produccion_por_operador_en_mes

    with app.app_context():
        u = User(username="prod_op", password_hash="x", is_admin=False, activo=True)
        db.session.add(u)
        db.session.flush()

        def _session_and_handover(start: str, end: str, stock: float) -> ShiftHandover:
            sess = ShiftSession(
                user_id=int(u.id),
                effective_role="operaciones",
                started_at_iso=start,
                ended_at_iso=end,
                status="closed",
                created_at_iso=start,
                updated_at_iso=end,
            )
            db.session.add(sess)
            db.session.flush()
            ho = ShiftHandover(
                shift_session_id=int(sess.id),
                outgoing_user_id=int(u.id),
                shift_started_at_iso=start,
                handed_over_at_iso=end,
                received_at_iso=end,
                hypochlorite_stock_liters=stock,
                status=sh.HANDOVER_RECEIVED,
                created_at_iso=end,
                updated_at_iso=end,
            )
            db.session.add(ho)
            db.session.flush()
            return ho

        _session_and_handover("2026-05-28T08:00:00", "2026-05-28T16:00:00", 10_000.0)
        _session_and_handover("2026-06-02T08:00:00", "2026-06-02T16:00:00", 12_000.0)
        db.session.commit()

        mes_junio = produccion_por_operador_en_mes(2026, 6)
        assert mes_junio["total_liters"] == 2_000.0
        assert len(mes_junio["operadores"]) == 1
        assert mes_junio["operadores"][0]["operador"] == "prod_op"
        assert mes_junio["operadores"][0]["produccion_liters"] == 2_000.0


def test_dashboard_operadores_route_requires_login(client):
    r = client.get("/dashboard/operadores", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_dashboard_operadores_route_ok(auth_client):
    r = auth_client.get("/dashboard/operadores")
    assert r.status_code == 200
    assert b"Ranking de atrasos" in r.data
    assert b"Producci" in r.data


def test_analisis_promedios_con_desvios(app):
    from app.extensions import db
    from app.models import ReactorRegistro, SalmueraRegistro
    from app.services.operador_dashboard_service import analisis_promedios_por_operador_en_mes

    with app.app_context():
        db.session.add(
            SalmueraRegistro(
                fecha_iso="2026-06-10",
                hora_hm="08:00",
                electrolizador=2,
                cantidad_celdas=6,
                turno="M",
                voltajes_json="[3.0,3.0,3.0,3.0,3.0,3.0]",
                voltaje_total=18.0,
                voltaje_total_trafo=110.0,
                amperaje=50.0,
                caudal_agua_l_h=10.0,
                caudal_salmuera_l_h=12.0,
                hipo_conc=1.0,
                hipo_exceso_soda=10.0,
                sal_temp=25.0,
                sal_conc=250.0,
                sal_ph=5.5,
                soda_conc=1.0,
                declor_ph=2.0,
                operador="op_reporte",
                created_at_iso="2026-06-10T08:00:00",
            )
        )
        db.session.add(
            SalmueraRegistro(
                fecha_iso="2026-06-11",
                hora_hm="08:00",
                electrolizador=2,
                cantidad_celdas=6,
                turno="M",
                voltajes_json="[3.0,3.0,3.0,3.0,3.0,3.0]",
                voltaje_total=18.0,
                voltaje_total_trafo=110.0,
                amperaje=52.0,
                caudal_agua_l_h=10.0,
                caudal_salmuera_l_h=12.0,
                hipo_conc=1.0,
                hipo_exceso_soda=8.0,
                sal_temp=25.0,
                sal_conc=270.0,
                sal_ph=4.5,
                soda_conc=1.0,
                declor_ph=1.5,
                operador="op_reporte",
                created_at_iso="2026-06-11T08:00:00",
            )
        )
        db.session.add(
            ReactorRegistro(
                fecha_iso="2026-06-10",
                hora_hm="09:00",
                operador="op_reporte",
                lote="L1",
                ph=7.0,
                temperatura=30.0,
                densidad=1.2,
                concentracion_tabla=195.0,
                exceso_naoh=0.2,
                exceso_na2co3=0.5,
                created_at_iso="2026-06-10T09:00:00",
            )
        )
        db.session.commit()

        data = analisis_promedios_por_operador_en_mes(2026, 6)
        assert "op_reporte" in data
        bloques = {b["tipo"]: b for b in data["op_reporte"]}
        hipo = bloques["hipoclorito_e2"]
        exceso = next(c for c in hipo["campos"] if c["key"] == "hipo_exceso_soda")
        assert exceso["promedio"] == 9.0
        assert exceso["desvios"] == 1
        assert hipo["total_desvios"] >= 3

        reactor = bloques["reactor"]
        assert reactor["total_desvios"] == 3


def test_inicio_reporte_visible_auth(auth_client):
    r = auth_client.get("/")
    assert r.status_code == 200
    assert b"Reporte por operador" in r.data
    assert b"desv" in r.data.lower()
