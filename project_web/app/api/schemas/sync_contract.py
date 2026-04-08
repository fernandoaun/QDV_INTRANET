from __future__ import annotations

from typing import TypedDict


class SyncMetaResponse(TypedDict):
    """Contrato de respuesta de GET /api/v1/sync/meta (documentación en código)."""

    api_version: int
    server_time_utc: str
