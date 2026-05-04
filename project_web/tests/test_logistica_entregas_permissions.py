from __future__ import annotations

import re
from datetime import datetime


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
        assert user_can_entregas_cargar_effective(user)
        assert user_can_entregas_entregar_effective(user)
        assert user_can_edit_entregas_any_action(user)


def test_gestion_shows_quick_entry_row(auth_client):
    r = auth_client.get("/entregas/gestion")

    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="entregaQuickForm"' in html
    assert "GUARDAR" in html
    assert "+ Programar" not in html


def test_quick_entry_creates_programada(auth_client, app):
    from app.extensions import db
    from app.models import ChoferEntrega, ClienteEntrega, Entrega, LugarEntrega, ProductoTerminado

    now = "2026-04-24T12:00:00"
    with app.app_context():
        cli = ClienteEntrega(nombre="Cliente Pytest", activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add(cli)
        db.session.flush()
        lug = LugarEntrega(nombre="Planta Cliente", cliente_id=int(cli.id), activo=True, created_at_iso=now, updated_at_iso=now)
        pt = ProductoTerminado(
            nombre="Producto Pytest",
            stock_producto="Producto Pytest",
            activo=True,
            created_at_iso=now,
            updated_at_iso=now,
        )
        ch = ChoferEntrega(nombre="Chofer Pytest", activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add_all([lug, pt, ch])
        db.session.commit()
        ids = (int(cli.id), int(lug.id), int(pt.id), int(ch.id))

    r = auth_client.get("/entregas/gestion")
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None

    r = auth_client.post(
        "/entregas/gestion",
        data={
            "csrf_token": m.group(1),
            "action": "programar_rapido",
            "fecha_prevista": "2026-04-25",
            "hora_prevista": "09:30",
            "cliente_id": str(ids[0]),
            "lugar_entrega_id": str(ids[1]),
            "producto_terminado_id": str(ids[2]),
            "cantidad": "1200",
            "chofer_entrega_id": str(ids[3]),
            "observaciones": "Alta rapida",
        },
        follow_redirects=False,
    )

    assert r.status_code in (302, 303)
    assert "quick_fecha=2026-04-25" in (r.headers.get("Location") or "")
    with app.app_context():
        ent = db.session.query(Entrega).filter_by(cliente="Cliente Pytest").one()
        assert ent.estado == "programada"
        assert ent.fecha_prevista == "2026-04-25"
        assert ent.chofer_previsto == "Chofer Pytest"
        assert ent.observaciones == "Hora prevista: 09:30\nAlta rapida"


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
