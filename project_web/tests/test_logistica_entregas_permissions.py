from __future__ import annotations

import re


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
