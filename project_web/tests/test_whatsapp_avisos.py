from __future__ import annotations

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import EmpleadoPersonal, User, WhatsappAviso
from app.services import whatsapp_avisos_service as svc

TOKEN = "whatsapp-test-token-32chars-minxx"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _empleado(legajo: str, email: str, telefono: str, *, estado: str = "activo", wa: str | None = None) -> None:
    uid = None
    if wa:
        u = User(username=f"u{legajo}", password_hash=generate_password_hash("x"), rol="operaciones", activo=True, whatsapp_e164=wa)
        db.session.add(u)
        db.session.flush()
        uid = u.id
    db.session.add(
        EmpleadoPersonal(user_id=uid, legajo=legajo, apellido="A", nombre=legajo, telefono=telefono, email=email, estado=estado)
    )
    db.session.commit()


def test_encolar_solo_destinatarios_con_legajo_y_celular(app):
    with app.app_context():
        _empleado("L1", "uno@qdv.ar", "299 15-4111111")
        _empleado("L2", "dos@qdv.ar", "", wa="+5492994222222")
        _empleado("L3", "baja@qdv.ar", "2994333333", estado="baja")
        _empleado("L4", "sintel@qdv.ar", "")
        n = svc.encolar_desde_mail(
            app, ["Uno@qdv.ar", "dos@qdv.ar", "baja@qdv.ar", "sintel@qdv.ar", "externo@gmail.com"], "Vence algo", "<p>Detalle</p>\n\n\n"
        )
        assert n == 2
        avisos = db.session.query(WhatsappAviso).order_by(WhatsappAviso.telefono_e164).all()
        assert [a.telefono_e164 for a in avisos] == ["+5492994111111", "+5492994222222"]
        assert avisos[0].texto == "*Vence algo*\n\nDetalle"


def test_encolar_respeta_interruptor(app):
    with app.app_context():
        _empleado("L1", "uno@qdv.ar", "2994111111")
        app.config["WHATSAPP_AVISOS_ENABLED"] = False
        assert svc.encolar_desde_mail(app, ["uno@qdv.ar"], "x", "y") == 0
        app.config["WHATSAPP_AVISOS_ENABLED"] = True


def test_api_avisos_pendientes_y_resultado(app, client):
    with app.app_context():
        _empleado("L1", "uno@qdv.ar", "2994111111")
        svc.encolar_desde_mail(app, ["uno@qdv.ar"], "Asunto", "Cuerpo")
    app.config["API_BEARER_TOKEN"] = TOKEN
    app.config["API_BEARER_USER_ID"] = None
    assert client.get("/api/v1/whatsapp/avisos").status_code == 401
    r = client.get("/api/v1/whatsapp/avisos", headers=H)
    assert r.status_code == 200
    avisos = r.get_json()["avisos"]
    assert len(avisos) == 1 and avisos[0]["telefono"] == "+5492994111111"
    aid = avisos[0]["id"]
    r = client.post(f"/api/v1/whatsapp/avisos/{aid}/resultado", headers=H, json={"ok": False, "error": "timeout"})
    assert r.get_json()["actualizado"] is True
    assert len(client.get("/api/v1/whatsapp/avisos", headers=H).get_json()["avisos"]) == 1
    client.post(f"/api/v1/whatsapp/avisos/{aid}/resultado", headers=H, json={"ok": True})
    assert client.get("/api/v1/whatsapp/avisos", headers=H).get_json()["avisos"] == []
