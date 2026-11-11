"""Informe diario de análisis por turno."""
from datetime import date

from app.extensions import db
from app.models import DeadlineReminderSent, PlantStopEvent, ReactorRegistro, ShiftSession, User
from app.services import informe_analisis_service as svc


def _reactor(fecha: str, hora: str, operador: str) -> None:
    db.session.add(ReactorRegistro(fecha_iso=fecha, hora_hm=hora, operador=operador, lote="P1", ph=12, temperatura=25,
                                   densidad=1.2, concentracion_tabla=10, exceso_naoh=5, exceso_na2co3=1,
                                   created_at_iso=f"{fecha}T{hora}:00"))


def test_esperados():
    assert svc.esperados(7200, 8 * 3600) == 4
    assert svc.esperados(8 * 3600, 8 * 3600) == 1
    assert svc.esperados(7200, 30 * 60) == 0


def test_informe_por_turno_y_persona(app, monkeypatch):
    with app.app_context():
        u = User(username="julian", nombre_completo="Torres, Julián", password_hash="x", rol="operaciones")
        db.session.add(u)
        db.session.flush()
        db.session.add(ShiftSession(user_id=u.id, effective_role="operaciones", status="closed", started_at_iso="2026-11-10T16:00:00",
                                    ended_at_iso="2026-11-11T00:00:00", created_at_iso="2026-11-10T16:00:00",
                                    updated_at_iso="2026-11-11T00:00:00"))
        for h in ("16:30", "18:40"):
            _reactor("2026-11-10", h, "julian")
        # Reactor parado toda la noche: no se esperan análisis de reactor en el turno N.
        db.session.add(PlantStopEvent(circuit_key="reactor", started_at_iso="2026-11-11T00:00:00",
                                      ended_at_iso="2026-11-11T08:00:00", operador="x", created_at_iso="2026-11-11T00:00:00"))
        db.session.commit()

        data = svc.armar(date(2026, 11, 10))
        tarde = next(t for t in data["turnos"] if t["codigo"] == "T")
        reactor = next(f for f in tarde["filas"] if f["nombre"] == "Reactor")
        assert (reactor["hechos"], reactor["esperados"], reactor["horas"]) == (2, 4, ["16:30", "18:40"])
        assert reactor["quien"] == {"Torres, Julián": 2}
        assert tarde["responsable"] == "Torres, Julián"
        noche = next(t for t in data["turnos"] if t["codigo"] == "N")
        assert next(f for f in noche["filas"] if f["nombre"] == "Reactor")["esperados"] == 0
        assert noche["personas"] == []
        persona = next(p for p in data["personas"] if p["nombre"] == "Torres, Julián")
        assert persona["hechos"] == 2 and persona["faltan"] > 0

        asunto, cuerpo_html, texto = svc.cuerpos(data)
        assert "10/11/2026" in asunto and "faltaron" in asunto
        assert "nadie abrió turno" in texto and "Torres, Julián" in cuerpo_html

        enviados = []
        monkeypatch.setattr(svc, "destinatarios", lambda app: ["a@b.com"])
        monkeypatch.setattr(svc, "is_mail_fully_configured", lambda app: True)
        monkeypatch.setattr(svc, "enviar_mail", lambda app, **kw: enviados.append(kw))
        assert svc.run_informe_analisis(app, dia=date(2026, 11, 10))["enviado"]
        assert not svc.run_informe_analisis(app, dia=date(2026, 11, 10))["enviado"]
        assert len(enviados) == 1
        assert db.session.query(DeadlineReminderSent).filter_by(domain="informe_analisis", entity_id=20261110).count() == 1
