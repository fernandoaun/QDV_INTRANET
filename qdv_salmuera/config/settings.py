from __future__ import annotations
import os

APP_TITLE = "Química del Valle - Panel Principal"

# Datos: SQLite local de esta app; no es la misma base que QDV Web (intranet).
# En planta con varios usuarios o acceso en red, la fuente de verdad operativa es project_web.

# Seguridad (borrado)
SECURITY_DELETE_CODE = "8956"

# Voltajes (circuito de salmuera)
VOLTAGE_MIN = 2.0
VOLTAGE_MAX = 4.5

# Cronómetro (2 horas)
ANALYSIS_INTERVAL_SECONDS = 2 * 60 * 60

# Operadores seed
DEFAULT_OPERATORS = ["Operador 1", "Operador 2", "Operador 3"]

def project_root() -> str:
    # .../qdv_salmuera/config/settings.py -> .../qdv_salmuera
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def assets_dir() -> str:
    return os.path.join(project_root(), "assets")

def db_path() -> str:
    # Compatibilidad: la DB ahora vive fuera de la carpeta del programa.
    # Usamos una ruta estable por usuario (AppData/Roaming por defecto).
    from qdv_salmuera.utils.app_paths import get_database_path

    return get_database_path(prefer_roaming=True)

def logo_path() -> str:
    return os.path.join(assets_dir(), "logo_qdv.png")
