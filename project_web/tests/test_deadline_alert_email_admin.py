from __future__ import annotations

import re

from flask import Flask


def test_avisos_correo_page_loads(auth_client):
    r = auth_client.get("/admin/avisos-correo")
    assert r.status_code == 200
    assert "Avisos por correo" in r.get_data(as_text=True)


def test_avisos_correo_add_and_merge(auth_client, app):
    r = auth_client.get("/admin/avisos-correo")
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    tok = m.group(1)
    r2 = auth_client.post(
        "/admin/avisos-correo/agregar",
        data={"csrf_token": tok, "email": "Foo@Test.COM"},
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)

    application = app
    assert isinstance(application, Flask)
    from app.services.deadline_alert_email_service import list_emails_ordered, merged_recipient_addresses

    with application.app_context():
        rows = list_emails_ordered()
        assert len(rows) == 1
        assert rows[0].email == "foo@test.com"
        merged = merged_recipient_addresses(application)
        assert merged == ["foo@test.com"]
