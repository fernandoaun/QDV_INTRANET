"""
Repositorios: consultas y persistencia orientadas a tablas/agregados.

Los servicios (app.services) orquestan reglas de negocio y llaman repositorios
cuando el acceso a datos se vuelve repetitivo o complejo.
"""

from app.repositories.base import BaseRepository
from app.repositories.entregas_repository import entregas_repo
from app.repositories.shift_repository import shift_repo
from app.repositories.stock_repository import stock_repo
from app.repositories.user_repository import user_repo

__all__ = ["BaseRepository", "entregas_repo", "shift_repo", "stock_repo", "user_repo"]
