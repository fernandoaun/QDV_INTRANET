from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AppPaths:
    data_dir: str
    db_path: str
    log_path: str


def _get_windows_appdata_base(prefer_roaming: bool = True) -> str:
    """
    En Windows usamos un directorio del usuario fuera de la carpeta del programa.
    - prefer_roaming=True  -> %APPDATA% (Roaming)
    - prefer_roaming=False -> %LOCALAPPDATA% (Local)
    """
    if prefer_roaming:
        base = os.environ.get("APPDATA")
        if base:
            return base
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return base
    # Fallback ultra defensivo: perfil del usuario
    return os.path.expanduser("~")


def get_app_data_dir(app_folder_name: str = "QuimicaDelValle\\QDV_Salmuera", *, prefer_roaming: bool = True) -> str:
    """
    Devuelve la carpeta persistente de la app (y la crea si no existe).

    Por defecto:
    - Windows: %APPDATA%\\QuimicaDelValle\\QDV_Salmuera
    """
    if os.name == "nt":
        base = _get_windows_appdata_base(prefer_roaming=prefer_roaming)
        data_dir = os.path.join(base, app_folder_name)
    else:
        # Linux/Mac fallback (por compatibilidad futura)
        data_dir = os.path.join(os.path.expanduser("~"), ".qdv_salmuera")

    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_database_path(db_filename: str = "salmuera.db", *, prefer_roaming: bool = True) -> str:
    data_dir = get_app_data_dir(prefer_roaming=prefer_roaming)
    return os.path.join(data_dir, db_filename)


def get_paths(*, prefer_roaming: bool = True) -> AppPaths:
    data_dir = get_app_data_dir(prefer_roaming=prefer_roaming)
    return AppPaths(
        data_dir=data_dir,
        db_path=os.path.join(data_dir, "salmuera.db"),
        log_path=os.path.join(data_dir, "qdv_salmuera.log"),
    )


def setup_persistent_logging(*, prefer_roaming: bool = True) -> None:
    """
    Log simple para diagnosticar ruta de DB y migraciones.
    - No rompe si no se puede escribir.
    """
    p = get_paths(prefer_roaming=prefer_roaming)
    try:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(p.log_path, encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )
    except Exception:
        # Si falla (permisos/antivirus), no frenamos la app.
        pass


def _legacy_project_db_path(project_root: str) -> str:
    # Históricamente: settings.db_path() -> project_root/salmuera.db
    return os.path.join(project_root, "salmuera.db")


def migrate_legacy_database_if_needed(*, project_root: str, prefer_roaming: bool = True) -> Optional[str]:
    """
    Migración automática (solo 1ra vez):
    - Si existe DB vieja en carpeta del programa/proyecto
    - y NO existe DB nueva en AppData
    => copiar a AppData (sin sobrescribir nunca la nueva)

    Devuelve un mensaje corto si migró (para log/UI), o None si no hizo nada.
    """
    new_db = get_database_path(prefer_roaming=prefer_roaming)
    if os.path.exists(new_db):
        return None

    legacy = _legacy_project_db_path(project_root)
    if not os.path.exists(legacy):
        return None

    os.makedirs(os.path.dirname(new_db), exist_ok=True)

    # Copia segura: legacy -> temp -> new_db
    tmp = new_db + ".tmp"
    try:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        shutil.copy2(legacy, tmp)
        os.replace(tmp, new_db)  # atómico en Windows si mismo volumen
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

    return f"Migración inicial: se copió DB legacy desde '{legacy}' hacia '{new_db}'."

