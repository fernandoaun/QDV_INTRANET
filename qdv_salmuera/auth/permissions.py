from __future__ import annotations

from typing import Dict, List, Tuple
from qdv_salmuera.ui.module_labels import module_label

# Claves estables guardadas en DB y usadas en código (no traducir)
PERMISSION_KEYS: List[str] = [
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

PERMISSION_LABELS: Dict[str, str] = {
    "produccion": "Producción (módulo)",
    "salmuera": module_label("salmuera"),
    "bolson_carga": "REALIZAR CONSUMO",
    "bolson_registro": "STOCK",
    "reactor": module_label("reactor"),
    "agua": module_label("agua"),
    "graficos": "Gráficos",
    "recepcion": "Recepción",
    "despacho": "Despacho",
    "admin_usuarios": "Administración de usuarios",
}


def all_permission_keys() -> Tuple[str, ...]:
    return tuple(PERMISSION_KEYS)
