from __future__ import annotations

PERMISSION_KEYS: list[str] = [
    "produccion",
    "entregas",
    "entregas_programar",
    "entregas_cargar",
    "entregas_entregar",
    "manual",
    "salmuera",
    "bolson_carga",
    "bolson_registro",
    "stock_hub",
    "stock_ingreso_mp",
    "stock_ingreso_lab",
    "stock_consumos",
    "stock_existencias",
    "stock_historial",
    "stock_alertas_config",
    "reactor",
    "agua",
    "graficos",
    "lab_reactivos",
    "recepcion",
    "despacho",
    "admin_usuarios",
    "planificacion",
    "mantenimiento",
    "mantenimiento_equipos",
    "mantenimiento_correctivos",
    "mantenimiento_preventivos",
    "mantenimiento_recursos",
    "mantenimiento_predictivo",
    "sgi_hub",
    "sgi_documentos_edit",
    "personal",
]

# Nombre del producto en catálogo de stock (producto terminado / ingresos / consumos).
# Es el nombre canónico único en el ledger para el hipoclorito operativo (turno + Panel + trazabilidad).
HIPOCLORITO_STOCK_NOMBRE_PRODUCTO: str = "Hipoclorito"

# Categoría de stock usada en entregas que descuentan producto terminado (p. ej. hipoclorito embotellado).
ENTREGAS_STOCK_CATEGORIA: str = "producto_terminado"

# Marca fija de trazabilidad comercial/almacén para producto terminado en entregas (p. ej. hipoclorito).
# No define un stock aparte ni modifica el tope operativo del Panel (turno).
ENTREGAS_MARCA_PRODUCTO_TERMINADO_TRAZA: str = "QDV"

# Nombre comercial en catálogo de productos terminados (entregas); equivale operativamente a HIPOCLORITO_STOCK_NOMBRE_PRODUCTO.
HIPOCLORITO_PRODUCTO_TERMINADO_NOMBRE: str = "Hipoclorito de Sodio"

# Variantes históricas u otras grafías de `Entrega.producto` / `ProductoTerminado.stock_producto` equivalentes al mismo producto.
HIPOCLORITO_ENTREGA_ALIASES_ADICIONALES: tuple[str, ...] = ()

MODULE_LABELS: dict[str, str] = {
    "salmuera": "CONTROL HIPOCLORITO",
    "reactor": "CIRCUITO DE SALMUERA",
    "agua": "CIRCUITO DE AGUA",
    "lab_reactivos": "REACTIVOS DE LABORATORIO",
}

PERMISSION_LABELS: dict[str, str] = {
    "produccion": "Producción (módulo)",
    "entregas": "Entregas (acceso al módulo)",
    "entregas_programar": "Entregas · Programar y editar",
    "entregas_cargar": "Entregas · Cargar camión (operaciones)",
    "entregas_entregar": "Entregas · Marcar entregada",
    "manual": "Manual de uso",
    "salmuera": MODULE_LABELS["salmuera"],
    "bolson_carga": "REALIZAR CONSUMO",
    "bolson_registro": "STOCK",
    "stock_hub": "Stock y consumos (módulo)",
    "stock_ingreso_mp": "Stock · Ingreso de materias primas",
    "stock_ingreso_lab": "Stock · Ingreso de laboratorio",
    "stock_consumos": "Stock · Consumos",
    "stock_existencias": "Stock · Existencias",
    "stock_historial": "Stock · Historial",
    "stock_alertas_config": "Stock · Configurar alertas",
    "reactor": MODULE_LABELS["reactor"],
    "agua": MODULE_LABELS["agua"],
    "graficos": "Gráficos",
    "lab_reactivos": "Reactivos de laboratorio",
    "recepcion": "Recepción",
    "despacho": "Despacho",
    "admin_usuarios": "Administración de usuarios",
    "planificacion": "Planificación y Gantt",
    "mantenimiento": "Mantenimiento (módulo)",
    "mantenimiento_equipos": "Mantenimiento · Equipos y componentes",
    "mantenimiento_correctivos": "Mantenimiento · Correctivos",
    "mantenimiento_preventivos": "Mantenimiento · Preventivos y órdenes",
    "mantenimiento_recursos": "Mantenimiento · Recursos y repuestos",
    "mantenimiento_predictivo": "Mantenimiento · Predictivo",
    "sgi_hub": "SGI – Sistema de Gestión Integrado (acceso)",
    "sgi_documentos_edit": "SGI · Crear y editar documentos",
    "personal": "Personal / RRHH (legajos, EPP, vacaciones)",
}

PERMISSION_TREE: list[dict[str, object]] = [
    {
        "key": "entregas",
        "label": "Entregas",
        "children": [
            {"key": "entregas_programar", "label": "Programar y editar entregas"},
            {"key": "entregas_cargar", "label": "Cargar en camión (operaciones, stock hipoclorito)"},
            {"key": "entregas_entregar", "label": "Marcar como entregada"},
        ],
    },
    {
        "key": "produccion",
        "label": "Producción",
        "children": [
            {"key": "salmuera", "label": MODULE_LABELS["salmuera"]},
            {"key": "reactor", "label": MODULE_LABELS["reactor"]},
            {"key": "agua", "label": MODULE_LABELS["agua"]},
            {"key": "bolson_registro", "label": "Bolson / registro horario"},
            {"key": "bolson_carga", "label": "Bolson / realizar consumo"},
            {"key": "graficos", "label": "Gráficos"},
            {"key": "lab_reactivos", "label": PERMISSION_LABELS["lab_reactivos"]},
        ],
    },
    {
        "key": "stock_hub",
        "label": "Stock y consumos",
        "children": [
            {"key": "stock_ingreso_mp", "label": "Ingreso de materias primas"},
            {"key": "stock_ingreso_lab", "label": "Ingreso de productos de laboratorio"},
            {"key": "stock_consumos", "label": "Consumos"},
            {"key": "stock_existencias", "label": "Existencias"},
            {"key": "stock_historial", "label": "Historial"},
            {"key": "stock_alertas_config", "label": "Alertas / configuración"},
        ],
    },
    {"key": "manual", "label": "Manual de uso", "children": []},
    {"key": "admin_usuarios", "label": "Administración de usuarios", "children": []},
    {"key": "recepcion", "label": "Recepción", "children": []},
    {"key": "despacho", "label": "Despacho", "children": []},
    {"key": "planificacion", "label": "Planificación y Gantt", "children": []},
    {
        "key": "mantenimiento",
        "label": "Mantenimiento",
        "children": [
            {"key": "mantenimiento_equipos", "label": "Equipos y componentes"},
            {"key": "mantenimiento_correctivos", "label": "Correctivos"},
            {"key": "mantenimiento_preventivos", "label": "Preventivos y órdenes"},
            {"key": "mantenimiento_recursos", "label": "Recursos y repuestos"},
            {"key": "mantenimiento_predictivo", "label": "Predictivo"},
        ],
    },
    {
        "key": "sgi_hub",
        "label": "SGI – Sistema de Gestión Integrado",
        "children": [
            {"key": "sgi_documentos_edit", "label": "Crear y editar documentos"},
        ],
    },
    {"key": "personal", "label": "Personal / RRHH", "children": []},
]


def _permission_form_keys_ordered() -> tuple[str, ...]:
    """Claves que el formulario admin envía (mismo orden que el árbol en pantalla)."""
    keys: list[str] = []
    for g in PERMISSION_TREE:
        keys.append(str(g["key"]))
        for c in g.get("children") or []:
            keys.append(str(c["key"]))
    return tuple(keys)


PERMISSION_FORM_KEYS: tuple[str, ...] = _permission_form_keys_ordered()

DEFAULT_OPERATORS = ["Operador 1", "Operador 2", "Operador 3"]

VOLTAGE_MIN = 2.0
VOLTAGE_MAX = 4.5
ANALYSIS_INTERVAL_SECONDS = 2 * 60 * 60
# Electrolizadores con formulario y cronómetro propio en pantalla (carga simultánea). Ampliar la tupla para sumar equipos.
SALMUERA_PANEL_ELECTROLIZADORES: tuple[int, ...] = (2, 3)
AGUA_ANALYSIS_INTERVAL_SECONDS = 8 * 60 * 60
SECURITY_DELETE_CODE = "8956"
