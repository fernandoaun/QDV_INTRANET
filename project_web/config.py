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
    }
    # Desarrollo local: que HTML/CSS/JS se lean de disco en cada request (evita “no veo los cambios”).
    if name not in ("production", "testing"):
        out["TEMPLATES_AUTO_RELOAD"] = True
        out["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    return out
