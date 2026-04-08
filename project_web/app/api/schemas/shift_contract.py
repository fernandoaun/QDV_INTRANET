from __future__ import annotations

from typing import TypedDict


class OpenShiftPayload(TypedDict):
    user_id: int
    operator_display: str


class ShiftStatusResponse(TypedDict):
    """Cuerpo JSON de GET /api/v1/shift/status (200)."""

    user_id: int
    participates_operational_shift: bool
    pending_handover: bool
    open_shift: OpenShiftPayload | None
    may_write_operational: bool
