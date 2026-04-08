from __future__ import annotations

from typing import Any, TypedDict


class DashboardSnapshotResponse(TypedDict, total=False):
    """
    Respuesta de GET /api/v1/dashboard/snapshot.
    Las claves presentes dependen de permisos (mismo criterio que el dashboard web).
    """

    alertas_stock: list[dict[str, Any]]
    ultimos_consumos_materia_prima: list[dict[str, Any]]
    ultimos_hipoclorito_por_rectificador: list[dict[str, Any]]
    ultimo_registro_reactor_salmuera: dict[str, Any] | None
    ultimo_registro_agua: dict[str, Any] | None
