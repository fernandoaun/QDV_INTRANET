from __future__ import annotations

from datetime import date, timedelta

from tests.test_planificacion_module import planif_client, planif_user  # noqa: F401


def test_ventana_mes_en_curso_sin_anticipo():
    from app.services import planificacion_service as ps

    assert ps.ventana_mes(date(2026, 10, 7)) == (date(2026, 10, 1), date(2026, 10, 31))


def test_ventana_mes_ultima_semana_suma_la_primera_del_siguiente():
    from app.services import planificacion_service as ps

    assert ps.ventana_mes(date(2026, 10, 26)) == (date(2026, 10, 1), date(2026, 11, 7))
    # Diciembre cruza de año.
    assert ps.ventana_mes(date(2026, 12, 30)) == (date(2026, 12, 1), date(2027, 1, 7))


def test_ventana_mes_otro_mes_no_suma_anticipo():
    from app.services import planificacion_service as ps

    assert ps.ventana_mes(date(2026, 10, 30), date(2026, 11, 1)) == (date(2026, 11, 1), date(2026, 11, 30))
    assert ps.parse_mes("2026-11") == date(2026, 11, 1)
    assert ps.parse_mes("basura") is None


def _crear(app, titulo, inicio, fin=None, estado="pendiente"):
    from app.extensions import db
    from app.models import PlanificacionActividad

    with app.app_context():
        fin = fin or inicio
        r = PlanificacionActividad(
            titulo=titulo,
            fecha_inicio=inicio,
            fecha_fin=fin,
            duracion_dias=PlanificacionActividad.compute_duracion_dias(inicio, fin),
            estado=estado,
        )
        db.session.add(r)
        db.session.commit()
        return r.id


def test_almanaque_muestra_solo_el_mes_y_las_atrasadas(planif_client, app):  # noqa: F811
    from app.services import planificacion_service as ps

    hoy = ps.now_operacion_naive_local().date()
    desde, hasta = ps.ventana_mes(hoy)
    _crear(app, "Tarea de este mes", desde)
    _crear(app, "Tarea muy lejana", hasta + timedelta(days=40))
    _crear(app, "Tarea vieja sin cumplir", desde - timedelta(days=3))
    _crear(app, "Tarea vieja cumplida", desde - timedelta(days=3), estado="finalizada")

    r = planif_client.get("/planificacion/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Tarea de este mes" in html
    assert "Tarea muy lejana" not in html
    assert "Pendientes de meses anteriores" in html
    assert "Tarea vieja sin cumplir" in html
    assert "Tarea vieja cumplida" not in html


def test_marcar_cumplida_desde_el_almanaque_responde_json(planif_client, app):  # noqa: F811
    from app.extensions import db
    from app.models import PlanificacionActividad

    aid = _crear(app, "Para cumplir", date.today())
    r = planif_client.post(
        f"/planificacion/estado/{aid}",
        data={"estado": "finalizada"},
        headers={"X-Requested-With": "fetch"},
    )
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "estado": "finalizada", "estado_label": "Finalizada"}
    with app.app_context():
        assert db.session.get(PlanificacionActividad, aid).estado == "finalizada"


def test_cambiar_estado_vuelve_al_almanaque_y_rechaza_next_externo(planif_client, app):  # noqa: F811
    aid = _crear(app, "Con next", date.today())
    r = planif_client.post(f"/planificacion/estado/{aid}?next=/planificacion/?mes=2026-10", data={"estado": "finalizada"})
    assert r.status_code in (302, 303)
    assert r.headers["Location"].endswith("/planificacion/?mes=2026-10")
    r = planif_client.post(f"/planificacion/estado/{aid}?next=https://evil.example/", data={"estado": "pendiente"})
    assert r.headers["Location"].endswith("/planificacion/tabla")


def test_tabla_por_defecto_limita_al_mes(planif_client, app):  # noqa: F811
    from app.services import planificacion_service as ps

    hoy = ps.now_operacion_naive_local().date()
    _, hasta = ps.ventana_mes(hoy)
    _crear(app, "Lejana en tabla", hasta + timedelta(days=40))
    html = planif_client.get("/planificacion/tabla").get_data(as_text=True)
    assert "Lejana en tabla" not in html
    html = planif_client.get("/planificacion/tabla?fecha_desde=2000-01-01&fecha_hasta=2100-01-01").get_data(as_text=True)
    assert "Lejana en tabla" in html
