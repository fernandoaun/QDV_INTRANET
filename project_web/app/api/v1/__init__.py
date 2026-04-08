from __future__ import annotations

from app.api.v1.blueprint import bp

# Carga rutas al importar el paquete.
from app.api.v1 import routes  # noqa: F401

__all__ = ["bp"]
