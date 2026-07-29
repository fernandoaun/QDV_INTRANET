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
        assert ent.carga_grupo_id
        assert ent.carga_origen_entrega_id is None


def test_logistica_asigna_carga_a_varias_entregas(auth_client, app, monkeypatch):
    from app.extensions import db
    from app.models import ChoferEntrega, ClienteEntrega, Entrega, LugarEntrega, ProductoTerminado
    from app.services import operational_informed_stock
    from app.services.entregas_service import entregas_kpis_rolling, es_origen_carga

    monkeypatch.setattr(operational_informed_stock, "get_instant_stock", lambda: 99999.0)

    now = "2026-07-24T12:00:00"
    with app.app_context():
        pt = ProductoTerminado(
            nombre="Hipoclorito Multi",
            stock_producto="Hipoclorito",
            activo=True,
            created_at_iso=now,
            updated_at_iso=now,
        )
        ch = ChoferEntrega(nombre="Chofer Multi", activo=True, created_at_iso=now, updated_at_iso=now)
        c1 = ClienteEntrega(nombre="Cliente A", activo=True, created_at_iso=now, updated_at_iso=now)
        c2 = ClienteEntrega(nombre="Cliente B", activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add_all([pt, ch, c1, c2])
        db.session.flush()
        l1 = LugarEntrega(nombre="Planta A", cliente_id=int(c1.id), activo=True, created_at_iso=now, updated_at_iso=now)
        l2 = LugarEntrega(nombre="Planta B", cliente_id=int(c2.id), activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add_all([l1, l2])
        db.session.commit()
        ids = {
            "pt": int(pt.id),
            "ch": int(ch.id),
            "c1": int(c1.id),
            "c2": int(c2.id),
            "l1": int(l1.id),
            "l2": int(l2.id),
        }

    r = auth_client.get("/entregas/gestion")
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    csrf = m.group(1)

    r = auth_client.post(
        "/entregas/gestion",
        data={
            "csrf_token": csrf,
            "action": "cargar_camion",
            "producto_terminado_id": str(ids["pt"]),
            "cantidad": "2000",
            "chofer_entrega_id": str(ids["ch"]),
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        origen = db.session.query(Entrega).filter_by(chofer_previsto="Chofer Multi").one()
        origen_id = int(origen.id)
        assert origen.estado == "cargada"
        assert origen.cantidad_real_cargada == 2000.0

    r = auth_client.get(f"/entregas/{origen_id}/editar")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="entregaMultiDestForm"' in html
    assert "Agregar entrega" in html
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None

    r = auth_client.post(
        f"/entregas/{origen_id}/editar",
        data={
            "csrf_token": m.group(1),
            "action": "asignar_multi",
            "fecha_prevista": "2026-07-24",
            "observaciones": "Reparto prueba",
            "dest_cliente_id": [str(ids["c1"]), str(ids["c2"])],
            "dest_lugar_entrega_id": [str(ids["l1"]), str(ids["l2"])],
            "dest_cantidad": ["1200", "800"],
            "dest_chofer_entrega_id": [str(ids["ch"]), str(ids["ch"])],
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        rows = (
            db.session.query(Entrega)
            .filter(Entrega.carga_grupo_id.isnot(None))
            .order_by(Entrega.id.asc())
            .all()
        )
        assert len(rows) == 2
        origen = rows[0]
        hermana = rows[1]
        assert origen.id == origen_id
        assert es_origen_carga(origen)
        assert origen.cliente == "Cliente A"
        assert origen.cantidad_programada == 1200.0
        assert origen.cantidad_real_cargada == 2000.0
        assert origen.consumo_stock_id is not None

        assert hermana.carga_origen_entrega_id == origen_id
        assert hermana.cliente == "Cliente B"
        assert hermana.cantidad_programada == 800.0
        assert hermana.cantidad_real_cargada is None
        assert hermana.consumo_stock_id is None
        assert hermana.estado == "cargada"
        assert hermana.cargada_at_iso == origen.cargada_at_iso

        kpis = entregas_kpis_rolling(dias=30)
        assert kpis["count_cargas"] == 1
        assert kpis["total_cargado"] == 2000.0
        assert kpis["count_entregas"] == 0


def test_assign_multi_rejects_volume_over_truck(app):
    from app.constants import ENTREGA_CLIENTE_PENDIENTE_LOGISTICA, ENTREGA_LUGAR_PENDIENTE_LOGISTICA
    from app.extensions import db
    from app.models import ChoferEntrega, ClienteEntrega, Entrega, LugarEntrega
    from app.services import entregas_web_service as ews

    now = "2026-07-24T12:00:00"
    with app.app_context():
        ch = ChoferEntrega(nombre="Chofer Over", activo=True, created_at_iso=now, updated_at_iso=now)
        c1 = ClienteEntrega(nombre="Cli Over", activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add_all([ch, c1])
        db.session.flush()
        l1 = LugarEntrega(nombre="Lugar Over", cliente_id=int(c1.id), activo=True, created_at_iso=now, updated_at_iso=now)
        origen = Entrega(
            cliente=ENTREGA_CLIENTE_PENDIENTE_LOGISTICA,
            lugar_entrega=ENTREGA_LUGAR_PENDIENTE_LOGISTICA,
            producto="Hipoclorito",
            cantidad=1000.0,
            cantidad_programada=1000.0,
            cantidad_real_cargada=1000.0,
            fecha_prevista="2026-07-24",
            estado="cargada",
            cargada_at_iso=now,
            created_at_iso=now,
            updated_at_iso=now,
            chofer_entrega_id=None,
            carga_grupo_id="test-grupo-over",
        )
        db.session.add_all([l1, origen])
        db.session.commit()

        try:
            ews.assign_logistica_multi_entregas(
                origen,
                [
                    {
                        "cliente_id": int(c1.id),
                        "lugar_entrega_id": int(l1.id),
                        "chofer_entrega_id": int(ch.id),
                        "cantidad": 600.0,
                    },
                    {
                        "cliente_id": int(c1.id),
                        "lugar_entrega_id": int(l1.id),
                        "chofer_entrega_id": int(ch.id),
                        "cantidad": 500.0,
                    },
                ],
                fecha_prevista="2026-07-24",
                observaciones=None,
                actor=None,
                at_iso=now,
            )
            raise AssertionError("expected ValueError")
        except ValueError as ex:
            assert "supera lo cargado" in str(ex)


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
