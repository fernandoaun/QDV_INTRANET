from __future__ import annotations

import os
from pathlib import Path


class BaseConfig:
    """Valores comunes (SECRET_KEY se lee en runtime en get_config_dict, después de load_dotenv)."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


def _default_sqlite_uri(base_dir: Path) -> str:
    instance = base_dir / "instance"
    instance.mkdir(parents=True, exist_ok=True)
    db_path = (instance / "qdv_web.db").resolve()
    return f"sqlite:///{db_path.as_posix()}"


def build_sqlalchemy_uri(base_dir: Path) -> str:
    """
    Prioridad: DATABASE_URL en entorno.
    Si no está, SQLite en instance/qdv_web.db bajo project_web.
    """
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        # Heroku-style postgres:// -> sqlalchemy
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://") :]
        elif url.startswith("postgresql://") and "+psycopg2" not in url:
            url = "postgresql+psycopg2://" + url[len("postgresql://") :]
        return url
    return _default_sqlite_uri(base_dir)


def get_config_name() -> str:
    return (os.environ.get("FLASK_ENV") or os.environ.get("ENV") or "development").strip().lower()


def get_config_dict(base_dir: Path) -> dict:
    name = get_config_name()
    if name == "production":
        cfg = ProductionConfig
    elif name == "testing":
        cfg = TestingConfig
    else:
        cfg = DevelopmentConfig

    secret_key = (os.environ.get("SECRET_KEY") or "").strip()
    if name == "production":
        if not secret_key:
            raise RuntimeError(
                "SECRET_KEY es obligatorio cuando FLASK_ENV=production. "
                "Definilo en variables de entorno del host (no en código)."
            )
    elif not secret_key:
        secret_key = "dev-only-change-me"

    db_url_env = (os.environ.get("DATABASE_URL") or "").strip()
    if name == "testing" and not db_url_env:
        uri = TestingConfig.SQLALCHEMY_DATABASE_URI
    elif name == "production":
        if not db_url_env:
            raise RuntimeError(
                "DATABASE_URL es obligatorio en producción (PostgreSQL). "
                "No uses SQLite en el servidor: creá una base en Render/Railway/VPS y enlazá la URL."
            )
        uri = build_sqlalchemy_uri(base_dir)
    else:
        uri = build_sqlalchemy_uri(base_dir)

    cookie_secure = (os.environ.get("SESSION_COOKIE_SECURE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    api_bearer_token = (os.environ.get("API_BEARER_TOKEN") or "").strip()
    api_uid_raw = (os.environ.get("API_BEARER_USER_ID") or "").strip()
    api_bearer_user_id: int | None = int(api_uid_raw) if api_uid_raw.isdigit() else None

    ratelimit_enabled = (os.environ.get("RATELIMIT_ENABLED") or "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if name == "testing":
        ratelimit_enabled = False
    ratelimit_default = (
        (os.environ.get("RATELIMIT_DEFAULT") or os.environ.get("RATELIMIT_API_DEFAULT") or "120 per minute").strip()
        or "120 per minute"
    )
    ratelimit_storage = (os.environ.get("RATELIMIT_STORAGE_URI") or "").strip() or "memory://"
    ratelimit_headers = (os.environ.get("RATELIMIT_HEADERS_ENABLED") or "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    api_docs_auth_raw = (os.environ.get("API_DOCS_REQUIRE_AUTH") or "").strip().lower()
    if name == "testing":
        api_docs_require_auth = False
    elif api_docs_auth_raw in ("1", "true", "yes"):
        api_docs_require_auth = True
    elif api_docs_auth_raw in ("0", "false", "no"):
        api_docs_require_auth = False
    else:
        api_docs_require_auth = name == "production"

    cors_raw = (os.environ.get("CORS_ORIGINS") or "").strip()
    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()] if cors_raw else []

    # Raíz persistente para PDFs (erlenmeyer), reactivos, etc. Equivale a instance/uploads.
    # En Render: montar Persistent Disk y apuntar aquí (ver DEPLOY_RENDER.md).
    app_upload_root = (os.environ.get("APP_UPLOAD_ROOT") or "").strip()

    inactivity_raw = (os.environ.get("SESSION_INACTIVITY_MINUTES") or "0").strip()
    try:
        session_inactivity_minutes = max(0, int(inactivity_raw))
    except ValueError:
        session_inactivity_minutes = 0

    login_ratelimit_enabled = name != "testing"
    login_rl_raw = (os.environ.get("LOGIN_RATELIMIT_ENABLED") or "").strip().lower()
    if login_rl_raw in ("0", "false", "no"):
        login_ratelimit_enabled = False
    elif login_rl_raw in ("1", "true", "yes"):
        login_ratelimit_enabled = True

    login_limit_minute = (
        os.environ.get("LOGIN_RATELIMIT_MINUTE") or ("1000 per minute" if name == "testing" else "12 per minute")
    ).strip()
    login_limit_hour = (
        os.environ.get("LOGIN_RATELIMIT_HOUR") or ("10000 per hour" if name == "testing" else "80 per hour")
    ).strip()

    sec_headers_raw = (os.environ.get("SECURITY_HEADERS_ENABLED") or "").strip().lower()
    if sec_headers_raw in ("0", "false", "no"):
        security_headers_enabled = False
    elif sec_headers_raw in ("1", "true", "yes"):
        security_headers_enabled = True
    else:
        security_headers_enabled = name != "testing"

    csp = (os.environ.get("CONTENT_SECURITY_POLICY") or "").strip()
    maintenance_attach_max_raw = (
        os.environ.get("MAINTENANCE_ATTACHMENT_MAX_BYTES") or str(12 * 1024 * 1024)
    ).strip()
    try:
        maintenance_attachment_max_bytes = int(maintenance_attach_max_raw)
    except ValueError:
        maintenance_attachment_max_bytes = 12 * 1024 * 1024
    if maintenance_attachment_max_bytes < 64 * 1024:
        maintenance_attachment_max_bytes = 64 * 1024

    analysis_pdf_max_raw = (
        os.environ.get("ANALYSIS_REF_PDF_MAX_BYTES") or str(15 * 1024 * 1024)
    ).strip()
    try:
        analysis_ref_pdf_max_bytes = int(analysis_pdf_max_raw)
    except ValueError:
        analysis_ref_pdf_max_bytes = 15 * 1024 * 1024

    analisis_8hs_max_raw = (
        os.environ.get("SALMUERA_ANALISIS_8HS_PDF_MAX_BYTES") or ""
    ).strip() or str(analysis_ref_pdf_max_bytes)
    try:
        salmuera_analisis_8hs_pdf_max_bytes = int(analisis_8hs_max_raw)
    except ValueError:
        salmuera_analisis_8hs_pdf_max_bytes = analysis_ref_pdf_max_bytes

    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()
    smtp_port_raw = (os.environ.get("SMTP_PORT") or "587").strip()
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        smtp_port = 587
    smtp_user = (os.environ.get("SMTP_USER") or "").strip()
    smtp_password = (os.environ.get("SMTP_PASSWORD") or "").strip()
    smtp_use_tls = (os.environ.get("SMTP_USE_TLS") or "true").strip().lower() in ("1", "true", "yes")
    mail_from = (os.environ.get("MAIL_FROM") or "").strip()
    deadline_mail_raw = (os.environ.get("DEADLINE_ALERT_EMAIL_TO") or "").strip()
    deadline_alert_email_to = [e.strip() for e in deadline_mail_raw.split(",") if e.strip()]
    deadline_days_raw = (os.environ.get("DEADLINE_REMINDER_DAYS_BEFORE") or "30").strip()
    try:
        deadline_reminder_days_before = int(deadline_days_raw)
    except ValueError:
        deadline_reminder_days_before = 30
    deadline_reminder_days_before = max(1, min(deadline_reminder_days_before, 366))

    out: dict = {
        "SECRET_KEY": secret_key,
        "DEBUG": getattr(cfg, "DEBUG", False),
        "TESTING": getattr(cfg, "TESTING", False),
        "WTF_CSRF_ENABLED": getattr(cfg, "WTF_CSRF_ENABLED", True),
        "SQLALCHEMY_DATABASE_URI": uri,
        "SQLALCHEMY_TRACK_MODIFICATIONS": cfg.SQLALCHEMY_TRACK_MODIFICATIONS,
        "SQLALCHEMY_ECHO": cfg.SQLALCHEMY_ECHO,
        "SESSION_COOKIE_SECURE": cookie_secure,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "API_BEARER_TOKEN": api_bearer_token,
        "API_BEARER_USER_ID": api_bearer_user_id,
        "RATELIMIT_ENABLED": ratelimit_enabled,
        "RATELIMIT_DEFAULT": ratelimit_default,
        "RATELIMIT_STORAGE_URI": ratelimit_storage,
        "RATELIMIT_HEADERS_ENABLED": ratelimit_headers,
        "API_DOCS_REQUIRE_AUTH": api_docs_require_auth,
        "CORS_ORIGINS": cors_origins,
        "APP_UPLOAD_ROOT": app_upload_root,
        "SESSION_INACTIVITY_MINUTES": session_inactivity_minutes,
        "LOGIN_RATELIMIT_ENABLED": login_ratelimit_enabled,
        "LOGIN_RATELIMIT_MINUTE": login_limit_minute,
        "LOGIN_RATELIMIT_HOUR": login_limit_hour,
        "SECURITY_HEADERS_ENABLED": security_headers_enabled,
        "CONTENT_SECURITY_POLICY": csp,
        "MAINTENANCE_ATTACHMENT_MAX_BYTES": maintenance_attachment_max_bytes,
        "ANALYSIS_REF_PDF_MAX_BYTES": analysis_ref_pdf_max_bytes,
        "SALMUERA_ANALISIS_8HS_PDF_MAX_BYTES": salmuera_analisis_8hs_pdf_max_bytes,
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": smtp_port,
        "SMTP_USER": smtp_user,
        "SMTP_PASSWORD": smtp_password,
        "SMTP_USE_TLS": smtp_use_tls,
        "MAIL_FROM": mail_from,
        "DEADLINE_ALERT_EMAIL_TO": deadline_alert_email_to,
        "DEADLINE_REMINDER_DAYS_BEFORE": deadline_reminder_days_before,
    }
    # Desarrollo local: que HTML/CSS/JS se lean de disco en cada request (evita “no veo los cambios”).
    if name not in ("production", "testing"):
        out["TEMPLATES_AUTO_RELOAD"] = True
        out["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    return out
