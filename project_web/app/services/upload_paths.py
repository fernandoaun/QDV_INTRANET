"""
Rutas de almacenamiento para cargas de usuario (PDFs erlenmeyer, reactivos, etc.).

En PaaS (p. ej. Render) el código se despliega en un filesystem **efímero**: todo lo que
no esté en la imagen o en un **disco persistente** se pierde al redesplegar.

- Escritura: siempre en `APP_UPLOAD_ROOT` si está definido; si no, en
  `%APPDATA%/QDV/erlenmeyer` (o `~/.qdv/erlenmeyer` fuera de Windows), fuera del código.
- Lectura: se prueba esa raíz, luego el legado `<instance_path>/uploads`, y después cada
  ruta en `APP_UPLOADS_READ_FALLBACK_PATHS` para no perder vínculo si el archivo existe en otro sitio.
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import current_app


def _default_persistent_upload_root() -> Path:
    appdata = (os.environ.get("APPDATA") or "").strip()
    if appdata:
        return Path(appdata).expanduser() / "QDV" / "erlenmeyer"
    return Path.home() / ".qdv" / "erlenmeyer"


def uploads_workspace_root() -> Path:
    """
    Directorio raíz del árbol de uploads (equivalente a ``instance/uploads`` en el diseño original).

    Debe apuntar a un volumen persistente en producción (variable ``APP_UPLOAD_ROOT``).
    """
    raw = (current_app.config.get("APP_UPLOAD_ROOT") or "").strip()
    if raw:
        base = Path(raw).expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base
    base = _default_persistent_upload_root().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def uploads_read_roots() -> list[Path]:
    """Orden: raíz de trabajo primero, luego fallbacks de solo lectura."""
    roots: list[Path] = [uploads_workspace_root()]
    legacy_instance_uploads = Path(current_app.instance_path).resolve() / "uploads"
    roots.append(legacy_instance_uploads)
    raw = (os.environ.get("APP_UPLOADS_READ_FALLBACK_PATHS") or "").strip()
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        try:
            roots.append(Path(p).expanduser().resolve())
        except OSError:
            continue
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        key = str(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def resolve_under_upload_roots(relative: Path) -> Path | None:
    """Si ``relative`` es relativo a la raíz ``uploads``, devuelve la primera ruta existente."""
    rel = relative
    if rel.is_absolute():
        return rel if rel.is_file() else None
    for root in uploads_read_roots():
        candidate = (root / rel).resolve()
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None
