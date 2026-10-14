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
    assert f"#{prog_id}" in resumen
    with app.app_context():
        directas = db.session.query(Entrega).filter_by(chofer_previsto="Rafa").order_by(Entrega.id).all()
        assert [(d.estado, d.cantidad_real_cargada) for d in directas] == [("cargada", 15000.0), ("cargada", 7000.0)]
        e = db.session.get(Entrega, prog_id)
        assert e.estado == "cargada" and e.cantidad_real_cargada == 9800.0 and e.cargada_by_user_id == uid
