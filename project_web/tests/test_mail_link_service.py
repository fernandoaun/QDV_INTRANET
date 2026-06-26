"""Tests para URLs absolutas en correos."""

from __future__ import annotations

from app.services.mail_link_service import login_url_for_path, public_abs_url


def test_public_abs_url_con_base_configurada(app):
    with app.app_context():
        app.config["APP_PUBLIC_BASE_URL"] = "https://ejemplo.com"
        url = public_abs_url(app, "personal.mis_entregas_epp")
    assert url == "https://ejemplo.com/personal/mis-entregas-epp"


def test_login_url_for_path(app):
    with app.app_context():
        app.config["APP_PUBLIC_BASE_URL"] = "https://ejemplo.com"
        url = login_url_for_path(app, "/personal/mis-entregas-epp")
    assert url.startswith("https://ejemplo.com/login?")
    assert "next=%2Fpersonal%2Fmis-entregas-epp" in url or "next=/personal/mis-entregas-epp" in url
