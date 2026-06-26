"""Tests para URLs absolutas en correos."""

from __future__ import annotations

from app.services.mail_link_service import (
    is_absolute_public_url,
    login_url_for_path,
    public_abs_url,
    require_absolute_mail_url,
    resolve_public_base,
)


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


def test_resolve_public_base_usa_render_external_url(app, monkeypatch):
    monkeypatch.setitem(app.config, "APP_PUBLIC_BASE_URL", "")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://qdv-demo.onrender.com")
    with app.app_context():
        assert resolve_public_base(app) == "https://qdv-demo.onrender.com"


def test_is_absolute_public_url_rechaza_ruta_relativa():
    assert not is_absolute_public_url("/personal/mis-entregas-epp")
    assert is_absolute_public_url("https://qdv.onrender.com/login?next=/personal/mis-entregas-epp")


def test_require_absolute_mail_url_bloquea_enlace_relativo(app):
    with app.app_context():
        ok, msg = require_absolute_mail_url(app, "/personal/mis-entregas-epp", context="test")
    assert not ok
    assert "APP_PUBLIC_BASE_URL" in msg
