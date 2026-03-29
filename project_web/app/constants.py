from __future__ import annotations

PERMISSION_KEYS: list[str] = [
    "produccion",
    "salmuera",
    "bolson_carga",
    "bolson_registro",
    "reactor",
    "agua",
    "graficos",
    "recepcion",
    "despacho",
    "admin_usuarios",
]

MODULE_LABELS: dict[str, str] = {
    "salmuera": "CONTROL HIPOCLORITO",
    "reactor": "CIRCUITO DE SALMUERA",
    "agua": "CIRCUITO DE AGUA",
}

PERMISSION_LABELS: dict[str, str] = {
    "produccion": "Producción (módulo)",
    "salmuera": MODULE_LABELS["salmuera"],
    "bolson_carga": "REALIZAR CONSUMO",
    "bolson_registro": "STOCK",
    "reactor": MODULE_LABELS["reactor"],
    "agua": MODULE_LABELS["agua"],
    "graficos": "Gráficos",
    "recepcion": "Recepción",
    "despacho": "Despacho",
    "admin_usuarios": "Administración de usuarios",
}

DEFAULT_OPERATORS = ["Operador 1", "Operador 2", "Operador 3"]

VOLTAGE_MIN = 2.0
VOLTAGE_MAX = 4.5
ANALYSIS_INTERVAL_SECONDS = 2 * 60 * 60
SECURITY_DELETE_CODE = "8956"
