from __future__ import annotations

import re
from datetime import date

import pytest

from app.services import planificacion_service as ps


def _rep(intervalo, unidad, veces=None, hasta=None):
    return ps.Repeticion(intervalo=intervalo, unidad=unidad, hasta=hasta, veces=veces)


def test_fechas_mensual_conserva_dia_y_ajusta_fin_de_mes():
    fechas, err = ps.fechas_repeticion(date(2026, 1, 31), date(2026, 2, 2), _rep(1, "meses", veces=4))
    assert err is None
    assert [i for i, _ in fechas] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    # Cada ocurrencia conserva la duración de la original (3 días inclusive).
    assert all((f - i).days == 2 for i, f in fechas)


def test_fechas_semanal_hasta_fecha():
    fechas, err = ps.fechas_repeticion(date(2026, 9, 1), date(2026, 9, 1), _rep(1, "semanas", hasta=date(2026, 9, 29)))
    assert err is None
    assert len(fechas) == 5
    assert fechas[-1][0] == date(2026, 9, 29)


def test_fechas_cada_10_anios_y_bisiesto():
    fechas, err = ps.fechas_repeticion(date(2024, 2, 29), date(2024, 2, 29), _rep(10, "anios", veces=3))
    assert err is None
    assert [i for i, _ in fechas] == [date(2024, 2, 29), date(2034, 2, 28), date(2044, 2, 29)]


def test_fechas_tope_y_sin_repeticion():
    _, err = ps.fechas_repeticion(date(2026, 1, 1), date(2026, 1, 1), _rep(1, "dias", hasta=date(2030, 1, 1)))
    assert err and "más de" in err
    _, err = ps.fechas_repeticion(date(2026, 1, 1), date(2026, 1, 1), _rep(1, "meses", hasta=date(2026, 1, 15)))
    assert err


@pytest.fixture
def planif_client(client, app):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(
            User(
                username="pytest_planif_rep",
                password_hash=generate_password_hash("pytest-planif-pw"),
                is_admin=False,
                activo=True,
                rol="operaciones",
            )
        )
        db.session.commit()
    html = client.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', html).group(1)
    r = client.post("/login", data={"username": "pytest_planif_rep", "password": "pytest-planif-pw", "csrf_token": tok})
    assert r.status_code in (302, 303)
    return client


def _serie(app, titulo):
    from sqlalchemy import select

    from app.extensions import db
    from app.models import PlanificacionActividad

    with app.app_context():
        rows = db.session.scalars(
            select(PlanificacionActividad)
            .where(PlanificacionActividad.titulo == titulo)
            .order_by(PlanificacionActividad.fecha_inicio)
        ).unique().all()
        return [(r.id, r.codigo, r.fecha_inicio, r.serie_id) for r in rows]


def test_crear_actividad_repetitiva_y_eliminar_siguientes(planif_client, app):
    r = planif_client.post(
        "/planificacion/nueva",
        data={
            "titulo": "Calibración mensual",
            "codigo": "CAL",
            "fecha_inicio": "2026-10-15",
            "fecha_fin": "2026-10-15",
            "estado": "pendiente",
            "prioridad": "media",
            "categoria": "mantenimiento",
            "repetir": "1",
            "rep_intervalo": "1",
            "rep_unidad": "meses",
            "rep_fin": "veces",
            "rep_veces": "6",
        },
    )
    assert r.status_code in (302, 303)
    rows = _serie(app, "Calibración mensual")
    assert [x[2] for x in rows] == [date(2026, m, 15) for m in (10, 11, 12)] + [date(2027, m, 15) for m in (1, 2, 3)]
    assert [x[1] for x in rows] == ["CAL-1", "CAL-2", "CAL-3", "CAL-4", "CAL-5", "CAL-6"]
    assert len({x[3] for x in rows}) == 1 and rows[0][3]

    ed = planif_client.get(f"/planificacion/editar/{rows[3][0]}")
    assert ed.status_code == 200
    assert "serie repetitiva de 6" in ed.get_data(as_text=True)
    assert "se repite" in planif_client.get("/planificacion/tabla").get_data(as_text=True)

    # Desde la 4.ª en adelante: quedan las 3 primeras.
    r = planif_client.post(f"/planificacion/eliminar-serie/{rows[3][0]}")
    assert r.status_code in (302, 303)
    assert [x[2] for x in _serie(app, "Calibración mensual")] == [date(2026, m, 15) for m in (10, 11, 12)]


def test_crear_sin_repetir_no_tiene_serie(planif_client, app):
    r = planif_client.post(
        "/planificacion/nueva",
        data={"titulo": "Única", "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-02", "rep_unidad": "meses"},
    )
    assert r.status_code in (302, 303)
    rows = _serie(app, "Única")
    assert len(rows) == 1 and rows[0][3] is None
