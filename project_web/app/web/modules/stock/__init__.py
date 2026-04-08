"""Stock operativo: ingresos, consumos, existencias, mínimos, historial.

Las rutas HTTP se registran en el blueprint ``produccion`` (endpoints
``produccion.stock_*``, URLs ``/produccion/stock``…) vía
``register_stock_routes`` en ``routes.py``. La lógica de negocio está en
``app.services.stock_service`` y ``app.repositories.stock_repository``.
"""

from app.web.modules.stock.routes import register_stock_routes

__all__ = ["register_stock_routes"]
