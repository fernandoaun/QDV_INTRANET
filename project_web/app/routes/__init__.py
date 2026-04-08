"""
Compatibilidad: imports del estilo ``from app.routes.main import bp``.

La implementación vive en ``app.web.modules.*``; cada módulo aquí solo reexporta el mismo blueprint.
"""

from app.routes import admin_users  # noqa: F401
from app.routes import auth  # noqa: F401
from app.routes import entregas  # noqa: F401
from app.routes import main  # noqa: F401
from app.routes import produccion  # noqa: F401
from app.routes import shift  # noqa: F401

__all__ = ["admin_users", "auth", "entregas", "main", "produccion", "shift"]
