from __future__ import annotations

from datetime import datetime, timezone

from app.api.schemas.sync_contract import SyncMetaResponse


def build_sync_meta() -> SyncMetaResponse:
    """
    Metadatos para clientes offline / PWA: versión de API y reloj del servidor (UTC).
    Los deltas y colas (outbox) se agregarán en este servicio o en uno dedicado sin cambiar la forma básica del dict.
    """
    return {
        "api_version": 1,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }
