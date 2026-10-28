"""Trazabilidad: lote de despacho ⇄ producción ⇄ lotes de materia prima (ver ``trazabilidad_service``)."""

from app.web.modules.trazabilidad.routes import bp

__all__ = ["bp"]
