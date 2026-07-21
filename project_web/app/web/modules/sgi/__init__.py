"""SGC – Sistema de Gestión de la Calidad (control documental)."""

from app.web.modules.sgi.routes import bp
from app.web.modules.sgi import procedure_routes  # noqa: F401 — registra rutas del editor visual

__all__ = ["bp"]
