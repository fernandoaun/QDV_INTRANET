"""Versión de la intranet y historial de actualizaciones (RELEASES.json en la raíz del proyecto web)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_RELEASES_PATH = Path(__file__).resolve().parents[2] / "RELEASES.json"


def _releases_path() -> Path:
    return _RELEASES_PATH


def _normalize_entry(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    version = (raw.get("version") or "").strip()
    desc = (raw.get("description") or raw.get("descripcion") or "").strip()
    if not version or not desc:
        return None
    date_raw = (raw.get("date") or raw.get("fecha") or "").strip()
    date_display = ""
    if len(date_raw) >= 10 and date_raw[4] == "-" and date_raw[7] == "-":
        date_display = f"{date_raw[8:10]}/{date_raw[5:7]}/{date_raw[:4]}"
    return {
        "version": version[:32],
        "date": date_raw[:10],
        "date_display": date_display,
        "description": desc[:500],
    }


@lru_cache(maxsize=1)
def _load_releases_cached(mtime_ns: int) -> dict[str, Any]:
    del mtime_ns
    path = _releases_path()
    if not path.is_file():
        return {"version": "0.0.0", "changelog": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": "0.0.0", "changelog": []}
    if not isinstance(data, dict):
        return {"version": "0.0.0", "changelog": []}
    version = (data.get("version") or "0.0.0").strip() or "0.0.0"
    changelog: list[dict[str, str]] = []
    for item in data.get("changelog") or []:
        row = _normalize_entry(item)
        if row:
            changelog.append(row)
    changelog.sort(key=lambda x: (x.get("date") or "", x.get("version") or ""), reverse=True)
    return {"version": version[:32], "changelog": changelog}


def load_releases() -> dict[str, Any]:
    path = _releases_path()
    mtime = int(path.stat().st_mtime_ns) if path.is_file() else 0
    return _load_releases_cached(mtime)


def app_release_context() -> dict[str, Any]:
    data = load_releases()
    return {
        "app_release_version": data["version"],
        "app_release_changelog": data["changelog"],
    }
