from __future__ import annotations

from datetime import date, timedelta

from tests.test_planificacion_module import planif_client, planif_user  # noqa: F401


def _lunes_proximo() -> date:
    hoy = date.today()
    return hoy + timedelta(days=7 - hoy.weekday())


def _crear_serie(client, titulo: str, inicio: date, dias_semana: list[str], veces: int = 6):
    data = {
        "titulo": titulo, "fecha_inicio": inicio.isoformat(), "fecha_fin": inicio.isoformat(),
        "estado": "pendiente", "prioridad": "media", "categoria": "mantenimiento",
        "repetir": "1", "rep_modo": "dias_semana", "rep_intervalo": "1", "rep_dias_semana": dias_semana,
        "rep_fin": "veces", "rep_veces": str(veces),
    }
    r = client.post("/planificacion/nueva", data=data)
    assert r.status_code in (302, 303)


def _serie(app, titulo):
    from sqlalchemy import select

    from app.extensions import db
    from app.models import PlanificacionActividad

    with app.app_context():
        rows = db.session.scalars(
            select(PlanificacionActividad).where(PlanificacionActividad.titulo.like(f"{titulo}%")).order_by(PlanificacionActividad.fecha_inicio)
        ).all()
        return [(r.id, r.titulo, r.fecha_inicio, r.estado, r.serie_id) for r in rows]


def _form_edit(row, titulo, **extra):
    _id, _t, ini, estado, _s = row
    data = {
        "titulo": titulo, "fecha_inicio": ini.isoformat(), "fecha_fin": ini.isoformat(),
        "estado": estado, "prioridad": "media", "categoria": "mantenimiento",
    }
    data.update(extra)
    return data


def test_editar_solo_esta_fecha(planif_client, app):  # noqa: F811
    _crear_serie(planif_client, "SoloEsta", _lunes_proximo(), ["0"])
    filas = _serie(app, "SoloEsta")
    r = planif_client.post(f"/planificacion/editar/{filas[2][0]}", data=_form_edit(filas[2], "SoloEsta cambiada", aplicar="esta"))
    assert r.status_code in (302, 303)
    titulos = [f[1] for f in _serie(app, "SoloEsta")]
    assert titulos.count("SoloEsta cambiada") == 1 and len(titulos) == 6


def test_cambiar_frecuencia_desde_una_fecha(planif_client, app):  # noqa: F811
    lunes = _lunes_proximo()
    _crear_serie(planif_client, "Frec", lunes, ["0"])  # lunes, 6 veces
    filas = _serie(app, "Frec")
    with app.app_context():
        from app.extensions import db
        from app.models import PlanificacionActividad

        db.session.get(PlanificacionActividad, filas[0][0]).estado = "finalizada"
        db.session.commit()
    # Desde la tercera: martes y jueves, 4 veces, con otro título.
    tercera = filas[2]
    martes = tercera[2] + timedelta(days=1)
    data = _form_edit(tercera, "Frec nueva", aplicar="siguientes", repetir="1", rep_modo="dias_semana",
                      rep_intervalo="1", rep_dias_semana=["1", "3"], rep_fin="veces", rep_veces="4")
    data["fecha_inicio"] = data["fecha_fin"] = martes.isoformat()
    r = planif_client.post(f"/planificacion/editar/{tercera[0]}", data=data)
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:500]
    filas2 = _serie(app, "Frec")
    viejas = [f for f in filas2 if f[1] == "Frec"]
    nuevas = [f for f in filas2 if f[1] == "Frec nueva"]
    # Las dos primeras quedan como estaban (una cumplida); desde la tercera, 4 fechas martes/jueves.
    assert [f[2] for f in viejas] == [lunes, lunes + timedelta(days=7)]
    assert viejas[0][3] == "finalizada"
    assert [f[2] for f in nuevas] == [martes, martes + timedelta(days=2), martes + timedelta(days=7), martes + timedelta(days=9)]
    assert len({f[4] for f in filas2}) == 1


def test_dejar_de_repetir(planif_client, app):  # noqa: F811
    _crear_serie(planif_client, "Corta", _lunes_proximo(), ["0"])
    filas = _serie(app, "Corta")
    r = planif_client.post(f"/planificacion/editar/{filas[1][0]}", data=_form_edit(filas[1], "Corta", aplicar="siguientes"))
    assert r.status_code in (302, 303)
    assert [f[0] for f in _serie(app, "Corta")] == [filas[0][0], filas[1][0]]


def test_convertir_tarea_suelta_en_repetitiva(planif_client, app):  # noqa: F811
    lunes = _lunes_proximo()
    r = planif_client.post("/planificacion/nueva", data={
        "titulo": "Suelta", "fecha_inicio": lunes.isoformat(), "fecha_fin": lunes.isoformat(),
        "estado": "pendiente", "prioridad": "media", "categoria": "otro",
    })
    assert r.status_code in (302, 303)
    fila = _serie(app, "Suelta")[0]
    assert fila[4] is None
    data = _form_edit(fila, "Suelta", repetir="1", rep_modo="dias_semana", rep_intervalo="1",
                      rep_dias_semana=["0"], rep_fin="veces", rep_veces="3")
    data["categoria"] = "otro"
    r = planif_client.post(f"/planificacion/editar/{fila[0]}", data=data)
    assert r.status_code in (302, 303)
    filas = _serie(app, "Suelta")
    assert [f[2] for f in filas] == [lunes, lunes + timedelta(days=7), lunes + timedelta(days=14)]
    assert filas[0][4] is not None and len({f[4] for f in filas}) == 1


def test_formulario_de_serie_precarga_la_frecuencia(planif_client, app):  # noqa: F811
    _crear_serie(planif_client, "Precarga", _lunes_proximo(), ["0", "3"])
    fila = _serie(app, "Precarga")[0]
    html = planif_client.get(f"/planificacion/editar/{fila[0]}").get_data(as_text=True)
    assert 'value="siguientes"' in html
    assert 'id="repDs0" checked' in html and 'id="repDs3" checked' in html
