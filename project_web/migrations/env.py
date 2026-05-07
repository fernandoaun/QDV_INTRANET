from __future__ import annotations

import logging
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")


def _get_app():
    os.environ["SKIP_SEED_DATA"] = "1"
    # create_app() exige SECRET_KEY en FLASK_ENV=production; Alembic solo usa DATABASE_URL y metadata.
    # Sin esto, el CMD Docker (alembic antes de gunicorn) falla si falta la variable en el entorno.
    if not (os.environ.get("SECRET_KEY") or "").strip():
        os.environ["SECRET_KEY"] = "_alembic_migration_placeholder_not_for_runtime"
    return create_app()


def run_migrations_offline() -> None:
    app = _get_app()
    url = app.config["SQLALCHEMY_DATABASE_URI"]
    context.configure(
        url=url,
        target_metadata=db.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    app = _get_app()
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
