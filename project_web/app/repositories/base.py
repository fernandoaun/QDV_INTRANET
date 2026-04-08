from __future__ import annotations

from app.extensions import db


class BaseRepository:
    """Acceso a datos vía sesión SQLAlchemy; sin lógica de negocio."""

    def __init__(self, session=None):
        self._session = session

    @property
    def session(self):
        return self._session if self._session is not None else db.session
