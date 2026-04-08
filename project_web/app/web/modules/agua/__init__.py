"""Circuito de agua (registros, historial, columnas de intercambio).

Rutas en blueprint ``produccion`` vía ``register_agua_routes``.
Helpers: ``app.web.modules.produccion.agua_helpers``.
"""

from app.web.modules.agua.routes import register_agua_routes

__all__ = ["register_agua_routes"]
