from __future__ import annotations

from sqlalchemy import func as sa_func
from sqlalchemy import select

from app.models import User
from app.repositories.base import BaseRepository
from app.user_roles import ROLE_LABORATORISTA, normalize_stored_rol


class UserRepository(BaseRepository):
    def get_by_id(self, uid: int) -> User | None:
        return self.session.get(User, int(uid))

    def find_active_by_username_ci(self, raw_username: str) -> User | None:
        key = (raw_username or "").strip().lower()
        if not key:
            return None
        return self.session.execute(
            select(User).where(sa_func.lower(User.username) == key)
        ).scalar_one_or_none()

    def list_active_laboratorista_users(self) -> list[User]:
        rows = list(
            self.session.scalars(
                select(User)
                .where(User.activo.is_(True), User.is_admin.is_(False))
                .order_by(User.username.asc())
            ).all()
        )
        return [u for u in rows if normalize_stored_rol(u.rol) == ROLE_LABORATORISTA]


user_repo = UserRepository()
