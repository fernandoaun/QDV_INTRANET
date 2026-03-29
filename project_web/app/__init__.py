from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from config import get_config_dict
from app.extensions import db


def create_app() -> Flask:
    base_dir = Path(__file__).resolve().parent.parent
    # En local, .env debe poder fijar SECRET_KEY y DATABASE_URL aunque existan vars vacías en el sistema.
    load_dotenv(base_dir / ".env", override=True)

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.config.from_mapping(get_config_dict(base_dir))
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(days=14))

    if app.config.get("DEBUG"):
        sk = (app.config.get("SECRET_KEY") or "").strip()
        if sk in ("", "dev-only-change-me"):
            app.logger.warning(
                "SECRET_KEY débil o por defecto: copiá .env.example a .env y definí SECRET_KEY para desarrollo."
            )

    db.init_app(app)

    from app import models  # noqa: F401  — registra metadata para Alembic

    with app.app_context():
        from app.bootstrap import ensure_seed_data

        ensure_seed_data()

    from app.cli import register_cli
    from app.routes.admin_users import bp as admin_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.main import bp as main_bp
    from app.routes.produccion import bp as produccion_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(produccion_bp)
    app.register_blueprint(admin_bp)

    register_cli(app)

    @app.context_processor
    def inject_nav_user():
        from app.auth_utils import current_user as _current_user
        from app.auth_utils import user_can as _user_can

        u = _current_user()
        return {
            "nav_user": u,
            "user_can": (lambda perm: _user_can(u, perm)),
        }

    @app.context_processor
    def inject_primera_vez():
        """Aviso si aún no hay usuarios (no existe clave por defecto en la web)."""
        from sqlalchemy import func, select

        from app.models import User

        try:
            n = db.session.scalar(select(func.count()).select_from(User))
            count = int(n or 0)
            return {
                "hay_usuarios_web": count > 0,
                "setup_db_ok": True,
            }
        except Exception:
            return {
                "hay_usuarios_web": False,
                "setup_db_ok": False,
            }

    return app
