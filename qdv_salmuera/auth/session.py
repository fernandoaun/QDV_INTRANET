from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class UserSession:
    user_id: int
    username: str
    is_admin: bool
    permissions: FrozenSet[str]

    def can(self, permiso: str) -> bool:
        if self.is_admin:
            return True
        return permiso in self.permissions
