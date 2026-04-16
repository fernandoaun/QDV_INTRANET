from __future__ import annotations

from flask import Blueprint

bp = Blueprint("export_historicos", __name__, url_prefix="/exportar-historicos")

from app.web.modules.export_historicos import routes  # noqa: E402, F401
