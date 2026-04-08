"""Blueprint ``produccion``: hub, circuitos de proceso, bolson, lab y gráficos.

La vista ``graficos`` vive en ``routes.py``; el resto se registra con ``register_*_routes``.
"""

from app.web.modules.produccion.routes import bp

__all__ = ["bp"]
