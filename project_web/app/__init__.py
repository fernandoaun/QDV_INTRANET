from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from config import get_config_dict
from app.extensions import csrf, db, limiter


def create_app() -> Flask:
    base_dir = Path(__file__).resolve().parent.parent
    # En local, .env fija SECRET_KEY / DATABASE_URL. No pisar FLASK_ENV o ENV ya definidos en el proceso
    # (p. ej. pytest o el shell exportó FLASK_ENV=testing antes de importar esta app).
    _flask_env = os.environ.get("FLASK_ENV")
    _env_name = os.environ.get("ENV")
    load_dotenv(base_dir / ".env", override=True)
    if _flask_env is not None:
        os.environ["FLASK_ENV"] = _flask_env
    if _env_name is not None:
        os.environ["ENV"] = _env_name

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
    limiter.init_app(app)
    csrf.init_app(app)

    @app.errorhandler(429)
    def _rate_limit_429(exc):
        from flask import jsonify, request

        if (request.path or "").startswith("/api/v1"):
            return jsonify(
                {
                    "error": "rate_limit",
                    "message": "Demasiadas solicitudes a la API. Probá más tarde.",
                }
            ), 429
        return exc

    from app.api import v1_bp as api_v1_bp
    from app.api.bearer import register_api_bearer

    register_api_bearer(api_v1_bp)
    app.register_blueprint(api_v1_bp)
    csrf.exempt(api_v1_bp)

    cors_origins = app.config.get("CORS_ORIGINS") or []
    if cors_origins:
        from flask_cors import CORS

        CORS(
            app,
            resources={r"/api/v1/*": {"origins": cors_origins}},
            supports_credentials=True,
            allow_headers=["Content-Type", "Authorization"],
            expose_headers=[
                "X-RateLimit-Limit",
                "X-RateLimit-Remaining",
                "X-RateLimit-Reset",
                "Retry-After",
            ],
            methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
        )

    if (app.config.get("API_BEARER_TOKEN") or "").strip() and app.config.get("API_BEARER_USER_ID") is None:
        app.logger.warning(
            "API_BEARER_TOKEN está definido pero falta API_BEARER_USER_ID válido: autenticación Bearer desactivada."
        )

    from app import models  # noqa: F401  — registra metadata para Alembic

    with app.app_context():
        if app.config.get("TESTING"):
            db.create_all()
        from app.bootstrap import ensure_seed_data

        if (os.environ.get("SKIP_SEED_DATA") or "").strip().lower() not in ("1", "true", "yes"):
            ensure_seed_data()

    from app.cli import register_cli
    from app.web.modules.admin import bp as admin_bp
    from app.web.modules.auth import bp as auth_bp
    from app.web.modules.entregas import bp as entregas_bp
    from app.web.modules.export_historicos import bp as export_historicos_bp
    from app.web.modules.panel import bp as main_bp
    from app.web.modules.produccion import bp as produccion_bp
    from app.web.modules.shift import bp as shift_bp
    from app.web.modules.planificacion import bp as planificacion_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(produccion_bp)
    app.register_blueprint(entregas_bp)
    app.register_blueprint(export_historicos_bp)
    app.register_blueprint(shift_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(planificacion_bp)

    @app.before_request
    def _guard_operational_shift_writes():
        from flask import flash, redirect, request, session, url_for

        from app.auth_utils import (
            current_user,
            endpoint_requires_operational_shift_for_post,
            user_shift_may_write_operational,
        )

        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        u = current_user()
        if u is None:
            return None
        ep = request.endpoint or ""
        if not endpoint_requires_operational_shift_for_post(ep):
            return None
        if user_shift_may_write_operational(u, session):
            return None
        flash(
            "Modo solo lectura: no podés modificar datos sin turno de planta activo a tu nombre.",
            "danger",
        )
        return redirect(request.referrer or url_for("main.dashboard"))

    from app.template_filters import register_template_filters

    register_template_filters(app)

    register_cli(app)

    @app.context_processor
    def inject_nav_user():
        from flask import session as flask_session

        from app.auth_utils import current_user as _current_user
        from app.auth_utils import page_can_edit_effective as _page_can_edit_effective
        from app.auth_utils import has_permission as _has_permission
        from app.auth_utils import user_can as _user_can
        from app.auth_utils import user_can_edit as _user_can_edit
        from app.auth_utils import user_can_view_admin_configuration as _user_can_view_admin_configuration
        from app.auth_utils import user_can_access_entregas_hub
        from app.auth_utils import user_can_access_planificacion
        from app.auth_utils import user_can_access_production_hub
        from app.auth_utils import (
            user_can_entregas_cargar_effective,
            user_can_entregas_entregar_effective,
            user_can_entregas_programar_effective,
        )
        from app.auth_utils import user_may_view_entregas_programar
        from app.auth_utils import (
            user_can_access_stock_hub,
            user_can_edit_stock_catalogo_alta,
            user_can_view_stock_existencias,
            user_can_view_stock_historial,
            user_can_view_stock_ingreso_categoria,
            user_can_view_stock_consumos,
        )
        from app.constants import MODULE_LABELS
        from app.services import planificacion_service as _planificacion_service
        from app.user_roles import ROLE_LABELS, USER_ROLES_ORDERED, role_label, user_is_global_read_only
        from flask import request

        u = _current_user()
        return {
            "nav_user": u,
            "user_can": (lambda perm: _user_can(u, perm)),
            "has_permission": (lambda perm: _has_permission(u, perm)),
            "user_can_edit": (lambda perm: _user_can_edit(u, perm)),
            "user_can_view_admin_configuration": (lambda: _user_can_view_admin_configuration(u)),
            "user_is_global_read_only": (lambda: user_is_global_read_only(u)),
            "page_can_edit_current": _page_can_edit_effective(u, request.endpoint, flask_session),
            "user_can_production_hub": user_can_access_production_hub(u),
            "user_can_entregas_hub": user_can_access_entregas_hub(u),
            "user_can_planificacion": user_can_access_planificacion(u),
            "user_can_entregas_programar": lambda: user_can_entregas_programar_effective(u),
            "user_can_entregas_programar_view": lambda: user_may_view_entregas_programar(u),
            "user_can_entregas_cargar": lambda: user_can_entregas_cargar_effective(u),
            "user_can_entregas_entregar": lambda: user_can_entregas_entregar_effective(u),
            "user_can_stock_hub": user_can_access_stock_hub(u),
            "user_can_stock_ingreso_mp": user_can_view_stock_ingreso_categoria(u, "materia_prima"),
            "user_can_stock_ingreso_lab": user_can_view_stock_ingreso_categoria(u, "laboratorio"),
            "user_can_stock_consumos": user_can_view_stock_consumos(u),
            "user_can_stock_existencias": user_can_view_stock_existencias(u),
            "user_can_stock_historial": user_can_view_stock_historial(u),
            "user_can_stock_catalogo_alta": user_can_edit_stock_catalogo_alta(u),
            "module_labels": MODULE_LABELS,
            "user_roles_ordered": USER_ROLES_ORDERED,
            "role_labels": ROLE_LABELS,
            "user_role_label": lambda u=None: role_label(getattr(u, "rol", None) if u is not None else None),
            "planificacion_display_codigo": _planificacion_service.actividad_display_codigo,
            "planificacion_is_atrasada": _planificacion_service.is_atrasada,
            "planificacion_resumen_predecesoras": lambda dlist: _planificacion_service.resumen_predecesoras_texto(dlist or []),
        }

    @app.context_processor
    def inject_header_operational_indicators():
        from app.services.operational_informed_stock import header_operational_indicators_dict

        d = header_operational_indicators_dict()
        return {
            "instant_stock": d["instant_display"],
            "last_shift_production": d["production_display"],
            "operational_indicators": d,
        }

    @app.context_processor
    def inject_shift_nav():
        from flask import request, session, url_for

        from app.auth_utils import current_user as _cu
        from app.auth_utils import user_shift_may_write_operational
        from app.services import shift_handover_service as sh

        u = _cu()
        if u is None or not sh.user_participates_operational_shift(u):
            return {"shift_nav": None}
        pending = sh.get_pending_handover()
        open_s = sh.get_open_shift_session()
        declined = bool(session.get(sh.SESSION_KEY_SHIFT_DECLINED))
        mine = open_s is not None and int(open_s.user_id) == int(u.id)
        other = open_s is not None and int(open_s.user_id) != int(u.id)
        operator_line = sh.format_shift_operator_display(open_s) if open_s is not None else ""
        other_name = operator_line if (other and open_s is not None) else ""
        may_write = user_shift_may_write_operational(u, session)
        ep = (request.endpoint or "").strip()
        show_readonly_pill = (not may_write) and (not ep.startswith("shift."))
        banner = None
        if pending is not None:
            banner = {
                "severity": "warning",
                "text": "Hay una entrega de turno pendiente de recepción.",
                "href": url_for("shift.take_shift"),
                "link_label": "Ir a recepcionar",
            }
        elif declined:
            banner = {
                "severity": "warning",
                "text": "Modo solo lectura: no tenés turno de planta tomado. Podés navegar y consultar; para cargar datos activá el turno.",
                "href": url_for("shift.take_shift"),
                "link_label": "Activar turno de planta",
            }
        elif other:
            banner = {
                "severity": "info",
                "text": "Modo solo lectura: el turno operativo lo tiene "
                + other_name
                + ". Podés consultar información; no podés registrar hasta que corresponda el cambio de turno.",
                "href": None,
                "link_label": None,
            }
        if ep.startswith("shift.") and banner and declined:
            banner = None
        return {
            "shift_nav": {
                "eligible": True,
                "open_mine": mine,
                "pending": pending is not None,
                "banner": banner,
                "show_readonly_pill": show_readonly_pill,
                "may_write_operational": may_write,
                "operator_line": operator_line if mine else "",
            }
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

    from config import get_config_name

    if get_config_name() == "production" and not (app.config.get("APP_UPLOAD_ROOT") or "").strip():
        app.logger.warning(
            "APP_UPLOAD_ROOT no está definido: PDFs de referencia (erlenmeyer) y adjuntos de reactivos se "
            "guardan en la carpeta persistente del usuario (%APPDATA%/QDV/erlenmeyer o ~/.qdv/erlenmeyer). "
            "En PaaS seguí definiendo APP_UPLOAD_ROOT apuntando a un volumen persistente; ver DEPLOY_RENDER.md."
        )

    return app
