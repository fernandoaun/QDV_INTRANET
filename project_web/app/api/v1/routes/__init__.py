"""Registra rutas sobre el blueprint api_v1 (import side effects)."""

from app.api.v1.routes import dashboard  # noqa: F401
from app.api.v1.routes import entregas  # noqa: F401
from app.api.v1.routes import health  # noqa: F401
from app.api.v1.routes import openapi  # noqa: F401
from app.api.v1.routes import shift  # noqa: F401
from app.api.v1.routes import stock  # noqa: F401
from app.api.v1.routes import sync  # noqa: F401
