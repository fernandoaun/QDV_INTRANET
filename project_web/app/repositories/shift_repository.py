from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import ShiftHandover, ShiftSession
from app.repositories.base import BaseRepository

# Valores alineados con modelos / shift_handover_service (evitar import circular).
_STATUS_OPEN = "open"
_HANDOVER_PENDING = "pending_reception"


def _shift_session_selectinloads():
    return (
        selectinload(ShiftSession.user),
        selectinload(ShiftSession.laboratorist_user),
    )


class ShiftRepository(BaseRepository):
    def get_open_shift_session(self) -> ShiftSession | None:
        return self.session.scalar(
            select(ShiftSession)
            .options(*_shift_session_selectinloads())
            .where(ShiftSession.status == _STATUS_OPEN)
            .limit(1)
        )

    def get_pending_handover(self) -> ShiftHandover | None:
        return self.session.scalar(
            select(ShiftHandover)
            .where(ShiftHandover.status == _HANDOVER_PENDING)
            .order_by(ShiftHandover.id.desc())
            .limit(1)
        )

    def get_shift_session_for_user(self, user_id: int) -> ShiftSession | None:
        return self.session.scalar(
            select(ShiftSession)
            .options(*_shift_session_selectinloads())
            .where(
                ShiftSession.user_id == user_id,
                ShiftSession.status == _STATUS_OPEN,
            )
        )

    def get_shift_session_by_id(self, session_id: int) -> ShiftSession | None:
        return self.session.get(ShiftSession, int(session_id))

    def list_handovers_for_history(self, limit: int = 200) -> list[ShiftHandover]:
        return list(
            self.session.scalars(
                select(ShiftHandover)
                .options(
                    selectinload(ShiftHandover.shift_session).selectinload(ShiftSession.user),
                    selectinload(ShiftHandover.shift_session).selectinload(ShiftSession.laboratorist_user),
                )
                .order_by(ShiftHandover.id.desc())
                .limit(limit)
            ).all()
        )


shift_repo = ShiftRepository()
