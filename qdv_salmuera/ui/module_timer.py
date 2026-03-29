from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

import tkinter as tk


@dataclass(frozen=True)
class TimerConfig:
    interval_seconds: int
    default_label: str


class PersistentModuleTimer:
    """
    Temporizador persistente tipo "Salmuera":
    - Calcula próximo deadline desde el último created_at_iso guardado.
    - Corre con after() cada 1s.
    - Permite reiniciar desde un created_at_iso luego de guardar.
    """

    def __init__(
        self,
        owner: tk.Misc,
        config: TimerConfig,
        fetch_last_created_at_iso: Callable[[], Optional[str]],
        out_var: tk.StringVar,
        on_overdue_change: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self.owner = owner
        self.config = config
        self.fetch_last_created_at_iso = fetch_last_created_at_iso
        self.out_var = out_var
        self.on_overdue_change = on_overdue_change

        self.next_due_dt: Optional[datetime] = None
        self._job = None
        self._overdue = False

    def _format_hhmmss(self, seconds: int) -> str:
        seconds = max(0, int(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _set_overdue(self, overdue: bool) -> None:
        overdue = bool(overdue)
        if overdue == self._overdue:
            return
        self._overdue = overdue
        if self.on_overdue_change:
            try:
                self.on_overdue_change(overdue)
            except Exception:
                pass

    def recompute_from_db(self) -> None:
        now = datetime.now()
        # default
        self.next_due_dt = now + timedelta(seconds=self.config.interval_seconds)

        last_iso = None
        try:
            last_iso = self.fetch_last_created_at_iso()
        except Exception:
            last_iso = None

        if last_iso:
            try:
                created = datetime.fromisoformat(last_iso)
                if created.tzinfo is not None:
                    created = created.astimezone().replace(tzinfo=None)
                self.next_due_dt = created + timedelta(seconds=self.config.interval_seconds)
            except Exception:
                self.next_due_dt = now + timedelta(seconds=self.config.interval_seconds)

        remaining = int((self.next_due_dt - now).total_seconds())
        remaining = max(0, remaining)
        self.out_var.set(self._format_hhmmss(remaining))
        self._set_overdue(remaining <= 0)

    def reset_from_created_at_iso(self, created_at_iso: str) -> None:
        try:
            created = datetime.fromisoformat(created_at_iso)
            if created.tzinfo is not None:
                created = created.astimezone().replace(tzinfo=None)
            self.next_due_dt = created + timedelta(seconds=self.config.interval_seconds)
        except Exception:
            self.next_due_dt = datetime.now() + timedelta(seconds=self.config.interval_seconds)

    def start(self) -> None:
        self.stop()
        # init label if empty
        if not (self.out_var.get() or "").strip():
            self.out_var.set(self.config.default_label)
        self.recompute_from_db()
        self._tick()

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.owner.after_cancel(self._job)
            except Exception:
                pass
        self._job = None

    def _tick(self) -> None:
        try:
            if hasattr(self.owner, "winfo_exists") and not self.owner.winfo_exists():
                return
        except Exception:
            return

        try:
            now = datetime.now()
            if self.next_due_dt is None:
                self.recompute_from_db()

            if self.next_due_dt is not None and getattr(self.next_due_dt, "tzinfo", None) is not None:
                self.next_due_dt = self.next_due_dt.astimezone().replace(tzinfo=None)

            remaining = int((self.next_due_dt - now).total_seconds())
            remaining = max(0, remaining)
            self.out_var.set(self._format_hhmmss(remaining))
            self._set_overdue(remaining <= 0)
        except Exception as e:
            try:
                self.out_var.set(f"ERR: {type(e).__name__}")
            except Exception:
                pass
        finally:
            self._job = self.owner.after(1000, self._tick)

