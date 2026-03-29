from __future__ import annotations

from datetime import datetime
from typing import Optional

import tkinter as tk

from qdv_salmuera.auth.session import UserSession


def get_current_user(widget: tk.Misc) -> Optional[UserSession]:
    current = widget
    while current is not None:
        session = getattr(current, "session", None)
        if isinstance(session, UserSession):
            return session
        current = getattr(current, "master", None)
    return None


def get_current_username(widget: tk.Misc) -> str:
    session = get_current_user(widget)
    return session.username if session else ""


def build_daily_lot(correlative: int, fecha_iso: Optional[str] = None) -> str:
    if fecha_iso:
        dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
    else:
        dt = datetime.now()
    return f"{dt.strftime('%y%m%d')}{correlative:02d}"
