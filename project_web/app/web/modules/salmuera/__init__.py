"""Circuito de salmuera (registros, historial, PDF hipo-conc histórico).

Las rutas se registran en el blueprint ``produccion`` vía ``register_salmuera_routes``.
Helpers de dominio: ``app.web.modules.produccion.salmuera_helpers``.
"""

from app.web.modules.salmuera.routes import register_salmuera_routes

__all__ = ["register_salmuera_routes"]
