from __future__ import annotations

import logging
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from flask import Flask
from sqlalchemy import engine_from_config, pool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import build_sqlalchemy_uri
from app.extensions import db

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")


def _migration_database_uri() -> str:
    """Solo migraciones: no pasar por get_config_dict (Docker / SECRET_KEY / resto de la app)."""
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        raise RuntimeError(
            "DATABASE_URL no está definida en el entorno del proceso. "
            "En Render (servicio Docker o Cron): Environment → agregá DATABASE_URL con la URL interna "
            "de PostgreSQL (la misma que usa tu base qdv-postgres). Los servicios Docker no heredan "
            "sola la variable del blueprint: copiala desde el recurso Postgres o desde el servicio web."
        )
    return build_sqlalchemy_uri(ROOT)


def _alembic_app() -> Flask:
    os.environ["SKIP_SEED_DATA"] = "1"
    import app.models  # noqa: F401 — registra tablas en db.metadata

    uri = _migration_database_uri()
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    db.init_app(app)
    return app


def run_migrations_offline() -> None:
    import app.models  # noqa: F401

    url = _migration_database_uri()
    context.configure(
        url=url,
        target_metadata=db.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    app = _alembic_app()
    with app.app_context():
        section = config.get_section(config.config_ini_section) or {}
        section["sqlalchemy.url"] = app.config["SQLALCHEMY_DATABASE_URI"]
        connectable = engine_from_config(
            section,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=db.metadata)

            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
