"""
Capa HTTP JSON (API REST) separada de las vistas HTML en app.routes / app.web.

Convención: la lógica de negocio vive en app.services; el acceso a datos
complejo en app.repositories; las rutas solo validan entrada, llaman servicios
y serializan salida.
"""

from app.api.v1 import bp as v1_bp

__all__ = ["v1_bp"]
