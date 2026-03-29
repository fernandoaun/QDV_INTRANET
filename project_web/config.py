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

    return {
        "SECRET_KEY": secret_key,
        "DEBUG": getattr(cfg, "DEBUG", False),
        "TESTING": getattr(cfg, "TESTING", False),
        "SQLALCHEMY_DATABASE_URI": uri,
        "SQLALCHEMY_TRACK_MODIFICATIONS": cfg.SQLALCHEMY_TRACK_MODIFICATIONS,
        "SQLALCHEMY_ECHO": cfg.SQLALCHEMY_ECHO,
        "SESSION_COOKIE_SECURE": cookie_secure,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
    }
