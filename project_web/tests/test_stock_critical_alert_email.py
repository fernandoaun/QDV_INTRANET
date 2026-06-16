from __future__ import annotations

import re
from unittest.mock import patch

from flask import Flask


def test_stock_critical_alert_email_add(auth_client, app):
    r = auth_client.get("/admin/avisos-correo")
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    r2 = auth_client.post(
        "/admin/avisos-correo/stock-critico/agregar",
        data={"csrf_token": m.group(1), "email": "Stock.Alert@Test.COM"},
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)

    application = app
    assert isinstance(application, Flask)
    from app.services.stock_alert_email_service import list_emails_ordered, merged_recipient_addresses

    with application.app_context():
        rows = list_emails_ordered()
        assert len(rows) == 1
        assert rows[0].email == "stock.alert@test.com"
        assert merged_recipient_addresses(application) == ["stock.alert@test.com"]


def test_critical_transition_sends_mail_once(app):
    from app.extensions import db
    from app.models import IngresoStock, ProductoCatalogo, StockCriticalAlertSent
    from app.services import stock_service
    from app.services.stock_alert_email_service import add_email

    with app.app_context():
        add_email("critico@test.com")
        stock_service.ensure_producto(
            "materia_prima",
            "Prod critico mail",
            stock_minimo_alerta=10.0,
            can_configure_alerta=True,
        )
        row = db.session.query(ProductoCatalogo).filter_by(nombre_producto="Prod critico mail").one()
        row.stock_minimo_alerta = 10.0
        db.session.commit()

        stock_service.save_ingreso(
            "materia_prima",
            "Prod critico mail",
            "Marca mail",
            "2027-12-31",
            "L-CRIT-1",
            12.0,
            "admin",
            fecha="2026-06-16",
            hora="10:00",
        )
        ingreso_id = int(
            db.session.query(IngresoStock).filter_by(producto="Prod critico mail").one().id
        )

        sent_calls: list[dict] = []

        def _fake_mail(application, *, destinatarios, asunto, cuerpo_html=None, cuerpo_texto=None, cc=None):
            sent_calls.append(
                {
                    "destinatarios": list(destinatarios),
                    "asunto": asunto,
                    "cuerpo_texto": cuerpo_texto,
                }
            )

        with patch("app.services.stock_critical_alert_service.enviar_mail", side_effect=_fake_mail):
            stock_service.save_consumo(
                "materia_prima",
                "Prod critico mail",
                "Marca mail",
                3.0,
                "admin",
                ingreso_stock_id=ingreso_id,
            )
            assert len(sent_calls) == 1
            assert sent_calls[0]["destinatarios"] == ["critico@test.com"]
            assert "Stock crítico" in sent_calls[0]["asunto"]
            assert db.session.query(StockCriticalAlertSent).count() == 1

            stock_service.save_consumo(
                "materia_prima",
                "Prod critico mail",
                "Marca mail",
                1.0,
                "admin",
                ingreso_stock_id=ingreso_id,
            )
            assert len(sent_calls) == 1

            class _Form:
                def get(self, key, default=""):
                    data = {
                        "categoria": "materia_prima",
                        "producto": "Prod critico mail",
                        "marca": "Marca mail",
                        "ingreso_stock_id": str(ingreso_id),
                        "tipo": "positivo",
                        "cantidad": "5",
                        "motivo": "Recuperación",
                        "observaciones": "",
                    }
                    return data.get(key, default)

            stock_service.save_ajuste_from_web_form(_Form(), operador="admin", admin_user_id=1)
            assert db.session.query(StockCriticalAlertSent).count() == 0
