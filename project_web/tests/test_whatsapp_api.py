from __future__ import annotations

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AguaRegistro, User
from app.services.whatsapp_identity import normalize_whatsapp_e164
from app.user_roles import ROLE_LABORATORISTA, ROLE_OPERACIONES, ROLE_SOLO_LECTURA_TOTAL

TOKEN = "whatsapp-test-token-32chars-minxx"
WA_ADMIN = "+5491110000001"
WA_ANGEL = "+5491110000002"
WA_LAB = "+5491110000003"
WA_OPS = "+5491110000004"


def test_normalize_whatsapp_e164():
    assert normalize_whatsapp_e164("+54 9 11 1000-0001") == "+5491110000001"
    assert normalize_whatsapp_e164("whatsapp:+5491110000001") == "+5491110000001"
    assert normalize_whatsapp_e164("5491110000001@s.whatsapp.net") == "+5491110000001"
    assert normalize_whatsapp_e164("") == ""
    assert normalize_whatsapp_e164("12") == ""


def test_normalize_whatsapp_e164_formatos_de_legajo():
    # Celulares argentinos como se cargan a mano -> como los manda WhatsApp (+549…).
    assert normalize_whatsapp_e164("3834 15-123456") == "+5493834123456"
    assert normalize_whatsapp_e164("03834 15 123456") == "+5493834123456"
    assert normalize_whatsapp_e164("(0351) 15-1234567") == "+5493511234567"
    assert normalize_whatsapp_e164("11 1000-0001") == "+5491110000001"
    assert normalize_whatsapp_e164("3834123456") == "+5493834123456"
    assert normalize_whatsapp_e164("+54 3834 123456") == "+5493834123456"
    assert normalize_whatsapp_e164("543834123456") == "+5493834123456"
    assert normalize_whatsapp_e164("0054 9 3834 123456") == "+5493834123456"
    assert normalize_whatsapp_e164("+1 415 555 0100") == "+14155550100"
    assert normalize_whatsapp_e164("123456") == ""


def test_whatsapp_numero_guardado_sin_9(app, client):
    with app.app_context():
        uid = _add_user(username="wa_sin9", rol="administrador", wa="+541110000009", is_admin=True)
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    r = client.get("/api/v1/me", headers=_headers("+5491110000009"))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["id"] == uid


def _add_user(*, username: str, rol: str, wa: str, is_admin: bool = False) -> int:
    u = User(
        username=username,
        password_hash=generate_password_hash("unused"),
        is_admin=is_admin,
        activo=True,
        rol=rol,
        whatsapp_e164=wa,
    )
    db.session.add(u)
    db.session.commit()
    return int(u.id)


def _headers(wa: str | None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    if wa:
        h["X-QDV-WhatsApp"] = wa
    return h


def test_whatsapp_header_resolves_user(app, client):
    with app.app_context():
        uid = _add_user(username="wa_admin", rol="administrador", wa=WA_ADMIN, is_admin=True)
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    r = client.get("/api/v1/me", headers=_headers(WA_ADMIN))
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["id"] == uid
    assert data["username"] == "wa_admin"
    assert data["channel"] == "whatsapp"
    assert data["whatsapp_e164"] == WA_ADMIN


def test_whatsapp_unknown_number_forbidden(app, client):
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    r = client.get("/api/v1/me", headers=_headers("+5491199999999"))
    assert r.status_code == 403
    assert "WhatsApp" in (r.get_json() or {}).get("message", "")


def test_bearer_without_user_id_or_whatsapp_unauthorized(app, client):
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    r = client.get("/api/v1/me", headers=_headers(None))
    assert r.status_code == 401


def test_laboratorista_whatsapp_forbidden(app, client):
    with app.app_context():
        _add_user(username="wa_lab", rol=ROLE_LABORATORISTA, wa=WA_LAB)
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    r = client.get("/api/v1/me", headers=_headers(WA_LAB))
    assert r.status_code == 403
    assert "laboratorista" in (r.get_json() or {}).get("message", "").lower()


def test_angel_can_read_not_write(app, client):
    with app.app_context():
        _add_user(username="wa_angel", rol=ROLE_SOLO_LECTURA_TOTAL, wa=WA_ANGEL)
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    me = client.get("/api/v1/me", headers=_headers(WA_ANGEL))
    assert me.status_code == 200
    assert me.get_json()["cargas"]["agua"] is False
    dash = client.get("/api/v1/dashboard/snapshot", headers=_headers(WA_ANGEL))
    assert dash.status_code == 200
    preview = client.post(
        "/api/v1/intents/preview",
        headers=_headers(WA_ANGEL),
        json={"module": "agua", "payload": {"numero_columna": 1, "temperatura": 20, "dureza": 1}},
    )
    assert preview.status_code == 403


def test_admin_preview_and_confirm_agua(app, client):
    with app.app_context():
        _add_user(username="wa_admin2", rol="administrador", wa=WA_ADMIN, is_admin=True)
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    preview = client.post(
        "/api/v1/intents/preview",
        headers=_headers(WA_ADMIN),
        json={
            "module": "agua",
            "payload": {"numero_columna": 1, "temperatura": 21.5, "dureza": 2.0},
            "source": "texto",
        },
    )
    assert preview.status_code == 200, preview.get_json()
    body = preview.get_json()
    assert body["needs_confirm"] is True
    token = body["confirm_token"]
    with app.app_context():
        assert db.session.query(AguaRegistro).count() == 0
    confirm = client.post(
        "/api/v1/intents/confirm",
        headers=_headers(WA_ADMIN),
        json={"confirm_token": token},
    )
    assert confirm.status_code == 200, confirm.get_json()
    assert confirm.get_json()["ok"] is True
    with app.app_context():
        assert db.session.query(AguaRegistro).count() == 1
    ultimo = client.get("/api/v1/produccion/agua/ultimo", headers=_headers(WA_ADMIN))
    assert ultimo.status_code == 200
    assert float(ultimo.get_json()["item"]["dureza"]) == 2.0


def test_operaciones_needs_shift_to_write(app, client):
    with app.app_context():
        _add_user(username="wa_ops", rol=ROLE_OPERACIONES, wa=WA_OPS)
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    preview = client.post(
        "/api/v1/intents/preview",
        headers=_headers(WA_OPS),
        json={"module": "agua", "payload": {"numero_columna": 1, "temperatura": 20, "dureza": 1}},
    )
    assert preview.status_code == 403
    assert "turno" in (preview.get_json() or {}).get("message", "").lower()


def test_openapi_documents_whatsapp_routes(client):
    spec = client.get("/api/v1/openapi.json").get_json()
    assert "/api/v1/me" in spec["paths"]
    assert "/api/v1/intents/preview" in spec["paths"]
    assert "WhatsAppIdentity" in spec["components"]["securitySchemes"]


def test_whatsapp_allowlist_desde_usuarios_y_legajos(app, client):
    from app.models import EmpleadoPersonal

    with app.app_context():
        _add_user(username="wa_admin", rol="administrador", wa=WA_ADMIN, is_admin=True)
        _add_user(username="wa_lab", rol=ROLE_LABORATORISTA, wa=WA_LAB)
        uid_leg = _add_user(username="wa_legajo", rol=ROLE_OPERACIONES, wa=None)
        db.session.add(EmpleadoPersonal(user_id=uid_leg, legajo="WA-1", apellido="Op", nombre="Uno", telefono="3834 15-123456"))
        uid_baja = _add_user(username="wa_baja", rol=ROLE_OPERACIONES, wa="+5491110000005")
        db.session.get(User, uid_baja).activo = False
        db.session.commit()
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    r = client.get("/api/v1/whatsapp/allowlist", headers=_headers(None))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["numeros"] == ["+5491110000001", "+5493834123456"]


def test_whatsapp_allowlist_exige_token(app, client):
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    assert client.get("/api/v1/whatsapp/allowlist").status_code == 401
    r = client.get("/api/v1/whatsapp/allowlist", headers={"Authorization": "Bearer otro-token"})
    assert r.status_code == 401
    app.config["API_BEARER_TOKEN"] = ""
    assert client.get("/api/v1/whatsapp/allowlist", headers=_headers(None)).status_code == 401


def test_chofer_carga_camion_por_whatsapp(app, client, monkeypatch):
    """Rafa (logística) carga su camión por el bot: carga directa y entrega programada."""
    from app.models import ChoferEntrega, Entrega, ProductoTerminado
    from app.services import operational_informed_stock
    from app.user_roles import ROLE_LOGISTICA

    monkeypatch.setattr(operational_informed_stock, "get_instant_stock", lambda: 99999.0)
    monkeypatch.setattr(operational_informed_stock, "get_carga_available", lambda: 99999.0)
    wa = "+5491110000011"
    now = "2026-10-13T10:00:00"
    with app.app_context():
        uid = _add_user(username="rafael", rol=ROLE_LOGISTICA, wa=wa)
        db.session.get(User, uid).nombre_completo = "Torres, Rafael"
        pt = ProductoTerminado(nombre="Hipoclorito Pytest", stock_producto="Hipoclorito", activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add_all([pt, ChoferEntrega(nombre="Mauri", activo=True, created_at_iso=now, updated_at_iso=now),
                            ChoferEntrega(nombre="Rafa", activo=True, created_at_iso=now, updated_at_iso=now)])
        db.session.flush()
        prog = Entrega(cliente="Cliente X", lugar_entrega="Planta X", producto="Hipoclorito", cantidad=10000, cantidad_programada=10000,
                       fecha_prevista="2026-10-13", estado="programada", created_at_iso=now, updated_at_iso=now, producto_terminado_id=int(pt.id))
        db.session.add(prog)
        db.session.commit()
        prog_id = int(prog.id)
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    assert client.get("/api/v1/me", headers=_headers(wa)).get_json()["cargas"]["carga_camion"] is True

    def cargar(payload):
        p = client.post("/api/v1/intents/preview", headers=_headers(wa), json={"module": "carga_camion", "payload": payload})
        assert p.status_code == 200, p.get_json()
        c = client.post("/api/v1/intents/confirm", headers=_headers(wa), json={"confirm_token": p.get_json()["confirm_token"]})
        assert c.status_code == 200, c.get_json()
        return p.get_json()["resumen"], c.get_json()

    resumen, _ = cargar({"litros": 15000})
    assert "chofer Rafa" in resumen
    # Nombres de campo inventados por el modelo (caso real de Rafa, 13/10/2026).
    resumen, _ = cargar({"litros_carga_camion": 7000, "chofer_nombre": "Rafa", "camion": "17-280"})
    assert "7000 L" in resumen and "chofer Rafa" in resumen
    resumen, _ = cargar({"litros": 9800, "entrega_id": prog_id})
    assert f"#{prog_id}" in resumen and "sin agua" in resumen
    resumen, _ = cargar({"litros": 6000, "agua_litros": 2000})
    assert "+ 2000 L de agua" in resumen
    with app.app_context():
        directas = db.session.query(Entrega).filter_by(chofer_previsto="Rafa").order_by(Entrega.id).all()
        assert [(d.estado, d.cantidad_real_cargada, d.agua_litros) for d in directas] == [
            ("cargada", 15000.0, None), ("cargada", 7000.0, None), ("cargada", 6000.0, 2000.0)]
        e = db.session.get(Entrega, prog_id)
        assert e.estado == "cargada" and e.cantidad_real_cargada == 9800.0 and e.cargada_by_user_id == uid


def test_chofer_descarga_en_varios_puntos_por_whatsapp(app, client, monkeypatch):
    """Rafa carga 7000 L sin destino y los descarga en dos puntos; el sistema lleva lo que queda en el camión."""
    from app.models import ChoferEntrega, ClienteEntrega, Entrega, LugarEntrega, ProductoTerminado
    from app.services import operational_informed_stock
    from app.user_roles import ROLE_LOGISTICA

    monkeypatch.setattr(operational_informed_stock, "get_instant_stock", lambda: 99999.0)
    monkeypatch.setattr(operational_informed_stock, "get_carga_available", lambda: 99999.0)
    wa = "+5491110000012"
    now = "2026-10-14T10:00:00"
    with app.app_context():
        uid = _add_user(username="rafael", rol=ROLE_LOGISTICA, wa=wa)
        db.session.get(User, uid).nombre_completo = "Torres, Rafael"
        db.session.add_all([
            ProductoTerminado(nombre="Hipoclorito Pytest", stock_producto="Hipoclorito", activo=True, created_at_iso=now, updated_at_iso=now),
            ChoferEntrega(nombre="Rafa", activo=True, created_at_iso=now, updated_at_iso=now),
        ])
        aguas = ClienteEntrega(nombre="Aguas", activo=True, created_at_iso=now, updated_at_iso=now)
        epas = ClienteEntrega(nombre="Epas Buena Esperanza", activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add_all([aguas, epas])
        db.session.flush()
        db.session.add_all([
            LugarEntrega(nombre="Buena Esperanza", cliente_id=aguas.id, activo=True, created_at_iso=now, updated_at_iso=now),
            LugarEntrega(nombre="Centenario", cliente_id=aguas.id, activo=True, created_at_iso=now, updated_at_iso=now),
            LugarEntrega(nombre="Cutral Co", cliente_id=epas.id, activo=True, created_at_iso=now, updated_at_iso=now),
        ])
        db.session.commit()
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    assert client.get("/api/v1/me", headers=_headers(wa)).get_json()["cargas"]["descarga_camion"] is True

    def preview(module, payload):
        return client.post("/api/v1/intents/preview", headers=_headers(wa), json={"module": module, "payload": payload})

    def hacer(module, payload):
        p = preview(module, payload)
        assert p.status_code == 200, p.get_json()
        c = client.post("/api/v1/intents/confirm", headers=_headers(wa), json={"confirm_token": p.get_json()["confirm_token"]})
        assert c.status_code == 200, c.get_json()
        return p.get_json()["resumen"], c.get_json()

    hacer("carga_camion", {"litros": 7000})
    # «Buena Esperanza» es ambiguo (lugar de Aguas y cliente Epas Buena Esperanza): pregunta cuál.
    amb = preview("descarga_camion", {"litros": 4000, "destino": "Buena Esperanza Cutral"})
    assert amb.status_code == 200  # con más palabras queda uno solo
    amb = preview("descarga_camion", {"litros": 4000, "destino": "Buena Esperanza"})
    assert amb.status_code == 400 and "¿Cuál?" in amb.get_json()["message"]

    resumen, out = hacer("descarga_camion", {"litros": 4000, "destino": "aguas buena esperanza"})
    assert "quedan 3000 L" in resumen and "Quedan 3000 L" in out["message"]
    exceso = preview("descarga_camion", {"litros": 3500, "destino": "Centenario"})
    assert exceso.status_code == 400 and "quedan 3000 L" in exceso.get_json()["message"]
    _, out = hacer("descarga_camion", {"litros_descargados": 3000, "destino": "Centenario"})
    assert "Camión vacío" in out["message"]
    assert preview("descarga_camion", {"litros": 100, "destino": "Centenario"}).status_code == 400

    with app.app_context():
        filas = db.session.query(Entrega).order_by(Entrega.id).all()
        assert [(e.lugar_entrega, e.estado, e.cantidad_real_entregada) for e in filas] == [
            ("Buena Esperanza", "entregada", 4000.0),
            ("Centenario", "entregada", 3000.0),
        ]
        assert filas[1].carga_origen_entrega_id == filas[0].id and filas[0].cantidad_real_cargada == 7000.0

    # Caso Mauri (14/10/2026): 4000 L de hipoclorito, después avisa 1000 L de agua mezclada y descarga la mezcla.
    _, out = hacer("carga_camion", {"litros": 4000})
    carga_id = out["id"]
    resumen, _ = hacer("carga_camion", {"entrega_id": carga_id, "agua_litros": 1000})
    assert f"1000 L de agua a la carga #{carga_id}" in resumen
    _, out = hacer("descarga_camion", {"litros": 800, "destino": "Centenario"})
    _, out = hacer("descarga_camion", {"litros": 4000, "destino": "Cutral Co"})
    assert "Quedan 200 L" in out["message"]
    with app.app_context():
        c = db.session.get(Entrega, carga_id)
        assert c.cantidad_real_cargada == 4000.0 and c.agua_litros == 1000.0


def test_descarga_web_sobre_destino_ya_asignado(app, auth_client, monkeypatch):
    """Si logística ya asignó ese destino, la descarga marca esa entrega (no crea otra)."""
    import re

    from app.models import ChoferEntrega, ClienteEntrega, Entrega, LugarEntrega, ProductoTerminado
    from app.services import operational_informed_stock

    monkeypatch.setattr(operational_informed_stock, "get_instant_stock", lambda: 99999.0)
    monkeypatch.setattr(operational_informed_stock, "get_carga_available", lambda: 99999.0)
    now = "2026-10-14T10:00:00"
    with app.app_context():
        pt = ProductoTerminado(nombre="Hipoclorito Pytest", stock_producto="Hipoclorito", activo=True, created_at_iso=now, updated_at_iso=now)
        ch = ChoferEntrega(nombre="Mauri", activo=True, created_at_iso=now, updated_at_iso=now)
        cli = ClienteEntrega(nombre="EPAS", activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add_all([pt, ch, cli])
        db.session.flush()
        lug = LugarEntrega(nombre="Chos Malal", cliente_id=cli.id, activo=True, created_at_iso=now, updated_at_iso=now)
        db.session.add(lug)
        db.session.flush()
        e = Entrega(cliente="EPAS", lugar_entrega="Chos Malal", cliente_id=cli.id, lugar_entrega_id=lug.id, producto="Hipoclorito",
                    cantidad=5000, cantidad_programada=5000, cantidad_real_cargada=5000, fecha_prevista="2026-10-14", estado="cargada",
                    chofer_previsto="Mauri", chofer_entrega_id=ch.id, producto_terminado_id=pt.id, cargada_at_iso=now,
                    created_at_iso=now, updated_at_iso=now)
        db.session.add(e)
        db.session.commit()
        eid, lid = e.id, lug.id
    html = auth_client.get("/entregas/gestion").get_data(as_text=True)
    assert f'id="modalDescargar{eid}"' in html
    token = re.search(r'name="csrf_token"\s+value="([^"]+)"', html).group(1)
    r = auth_client.post("/entregas/gestion", data={"csrf_token": token, "action": "descargar", "entrega_id": eid,
                                                    "lugar_entrega_id": lid, "cantidad_real": "4950"})
    assert r.status_code in (302, 303)
    with app.app_context():
        filas = db.session.query(Entrega).all()
        assert len(filas) == 1 and filas[0].estado == "entregada" and filas[0].cantidad_real_entregada == 4950.0
