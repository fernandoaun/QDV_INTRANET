from __future__ import annotations

import re
from datetime import datetime


def test_operaciones_cargar_does_not_require_active_shift(app):
    from flask import session

    from app.auth_utils import user_can_entregas_cargar_effective
    from app.models import User
    from app.user_roles import ROLE_OPERACIONES

    user = User(username="pytest_oper", password_hash="x", is_admin=False, activo=True, rol=ROLE_OPERACIONES)

    with app.test_request_context("/entregas/gestion"):
        session["perms"] = ["entregas", "entregas_cargar"]
        session["perms_edit"] = ["entregas", "entregas_cargar"]
        assert user_can_entregas_cargar_effective(user)


def test_logistica_can_operate_entregas_even_with_stale_session(app):
    from flask import session

    from app.auth_utils import (
        user_can_access_entregas_hub,
        user_can_entregas_cargar_effective,
        user_can_entregas_entregar_effective,
        user_can_entregas_programar_effective,
        user_can_edit_entregas_any_action,
    )
    from app.models import User
    from app.user_roles import ROLE_LOGISTICA

    user = User(username="pytest_logistica", password_hash="x", is_admin=False, activo=True, rol=ROLE_LOGISTICA)

    with app.test_request_context("/entregas/gestion"):
        session["perms"] = []
        session["perms_edit"] = []

        assert user_can_access_entregas_hub(user)
        assert user_can_entregas_programar_effective(user)
        assert not user_can_entregas_cargar_effective(user)
        assert user_can_entregas_entregar_effective(user)
        assert user_can_edit_entregas_any_action(user)


def test_gestion_shows_carga_camion_row(auth_client):
    r = auth_client.get("/entregas/gestion")

    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="entregaCargaCamionForm"' in html
    assert "CARGAR CAMIÓN" in html
    assert 'value="programar_rapido"' not in html
    assert "GUARDAR" not in html


def test_operador_hub_muestra_historial_y_catalogos(client, app):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import PermisoUsuario, User
    from app.user_roles import ROLE_OPERACIONES

    with app.app_context():
        u = User(
            username="pytest_oper_hub",
            password_hash=generate_password_hash("pytest-oper-pw"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add(u)
        db.session.flush()
        for p, edit in (("entregas", True), ("entregas_cargar", True)):
            db.session.add(
                PermisoUsuario(
                    user_id=int(u.id),
                    permiso=p,
                    habilitado=True,
                    puede_editar=edit,
                )
            )
        db.session.commit()

    lg = client.get("/login")
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', lg.get_data(as_text=True))
    assert m is not None
    r = client.post(
        "/login",
        data={"username": "pytest_oper_hub", "password": "pytest-oper-pw", "csrf_token": m.group(1)},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    r = client.get("/entregas/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Historial de entregas" in html
    assert "Catálogos de entregas" in html
    assert "Programar entrega" in html


def test_carga_camion_creates_cargada_pending_logistica(auth_client, app, monkeypatch):
    from app.constants import ENTREGA_CLIENTE_PENDIENTE_LOGISTICA
    from app.extensions import db
    from app.models import ChoferEntrega, Entrega, ProductoTerminado
    from app.services import operational_informed_stock
    from app.services.entregas_service import entrega_pendiente_logistica

    monkeypatch.setattr(operational_informed_stock, "get_instant_stock", lambda: 99999.0)

    now = "2026-04-24T12:00:00"
    with app.app_context():
        pt = ProductoTerminado(
            nombre="Hipoclorito Pytest",
            stock_producto="Hipoclorito",
            activo=True,
            created_at_iso=now,
            updated_at_iso=now,
        )
        ch = ChoferEntrega(nombre="Chofer Pytest", activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add_all([pt, ch])
        db.session.commit()
        ids = (int(pt.id), int(ch.id))

    r = auth_client.get("/entregas/gestion")
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None

    r = auth_client.post(
        "/entregas/gestion",
        data={
            "csrf_token": m.group(1),
            "action": "cargar_camion",
            "producto_terminado_id": str(ids[0]),
            "cantidad": "1500",
            "chofer_entrega_id": str(ids[1]),
        },
        follow_redirects=False,
    )

    assert r.status_code in (302, 303)
    with app.app_context():
        ent = db.session.query(Entrega).filter_by(chofer_previsto="Chofer Pytest").one()
        assert ent.estado == "cargada"
        assert ent.cantidad_real_cargada == 1500.0
        assert ent.cantidad_programada == 1500.0
        assert ent.cliente == ENTREGA_CLIENTE_PENDIENTE_LOGISTICA
        assert entrega_pendiente_logistica(ent)


def test_gestion_includes_previous_week_cargada_pending_delivery(app, monkeypatch):
    from app.extensions import db
    from app.models import Entrega
    from app.services import entregas_service

    monkeypatch.setattr(entregas_service, "now_operacion_naive_local", lambda: datetime(2026, 5, 6, 12, 0, 0))
    now = "2026-05-06T12:00:00"

    with app.app_context():
        old_programada = Entrega(
            cliente="Cliente programada",
            lugar_entrega="Lugar",
            producto="Producto",
            cantidad=100.0,
            cantidad_programada=100.0,
            fecha_prevista="2026-04-30",
            estado="programada",
            created_at_iso=now,
            updated_at_iso=now,
        )
        old_cargada = Entrega(
            cliente="Cliente cargada",
            lugar_entrega="Lugar",
            producto="Producto",
            cantidad=200.0,
            cantidad_programada=200.0,
            cantidad_real_cargada=200.0,
            fecha_prevista="2026-04-30",
            estado="cargada",
            cargada_at_iso="2026-04-30T10:00:00",
            created_at_iso=now,
            updated_at_iso=now,
        )
        old_entregada = Entrega(
            cliente="Cliente entregada",
            lugar_entrega="Lugar",
            producto="Producto",
            cantidad=300.0,
            cantidad_programada=300.0,
            fecha_prevista="2026-04-30",
            estado="entregada",
            entregada_at_iso="2026-04-30T11:00:00",
            created_at_iso=now,
            updated_at_iso=now,
        )
        current_entregada = Entrega(
            cliente="Cliente semana actual",
            lugar_entrega="Lugar",
            producto="Producto",
            cantidad=400.0,
            cantidad_programada=400.0,
            fecha_prevista="2026-05-04",
            estado="entregada",
            entregada_at_iso="2026-05-04T11:00:00",
            created_at_iso=now,
            updated_at_iso=now,
        )
        db.session.add_all([old_programada, old_cargada, old_entregada, current_entregada])
        db.session.commit()

        visible_clientes = [e.cliente for e in entregas_service.listar_entregas()]

    assert visible_clientes == ["Cliente programada", "Cliente cargada", "Cliente semana actual"]
