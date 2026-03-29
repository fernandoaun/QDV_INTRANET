from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from qdv_salmuera.auth.passwords import verify_password
from qdv_salmuera.auth.permissions import all_permission_keys
from qdv_salmuera.auth.session import UserSession

if TYPE_CHECKING:
    from qdv_salmuera.data.db import DB


def login(db: "DB", username: str, password: str) -> Optional[UserSession]:
    u = db.fetch_usuario_by_username(username)
    if not u:
        return None
    if not u.get("activo", 0):
        return None
    if not verify_password(u.get("password_hash") or "", password):
        return None
    is_admin = bool(u.get("is_admin", 0))
    if is_admin:
        perms = frozenset(all_permission_keys())
    else:
        perms = frozenset(db.fetch_permisos_habilitados(u["id"]))
    return UserSession(
        user_id=int(u["id"]),
        username=str(u["username"]),
        is_admin=is_admin,
        permissions=perms,
    )
