#!/usr/bin/env python3
"""Warn if local QDV setup risks mixing local SQLite with remote DB / secrets in git."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root (…/qdv_salmuera)
PROJECT_WEB = ROOT / "project_web"
ENV_PATH = PROJECT_WEB / ".env"

WARN_HEADER = "ADVERTENCIA — aislamiento de base local"


def _repo_root_from_git() -> Path | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return Path(out) if out else None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def check_env_database_url(env_path: Path) -> list[str]:
    issues: list[str] = []
    if not env_path.is_file():
        return issues
    raw = env_path.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^DATABASE_URL\s*=", stripped, flags=re.IGNORECASE):
            value = stripped.split("=", 1)[1].strip().strip("\"'")
            if value:
                issues.append(
                    f"{env_path.as_posix()}:{i} define DATABASE_URL={value!r}. "
                    "En local dejalo sin definir para usar SQLite."
                )
    return issues


def check_git_staged(repo: Path) -> list[str]:
    issues: list[str] = []
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "-z"],
            cwd=repo,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return issues
    if not out:
        return issues
    names = [n.decode("utf-8", errors="replace") for n in out.split(b"\0") if n]
    blocked_suffixes = (".db", ".db-shm", ".db-wal")
    for name in names:
        norm = name.replace("\\", "/")
        base = Path(norm).name
        if base == ".env" or norm.endswith("/.env") or "/.env." in f"/{norm}":
            if not norm.endswith(".env.example"):
                issues.append(f"Archivo sensible en staging: {norm}")
        if "/instance/" in f"/{norm}" or norm.startswith("instance/"):
            issues.append(f"Carpeta instance/ en staging: {norm}")
        if base.endswith(blocked_suffixes) or any(base.endswith(s) for s in blocked_suffixes):
            issues.append(f"Base SQLite en staging: {norm}")
    return issues


def main() -> int:
    repo = _repo_root_from_git() or ROOT
    env_path = repo / "project_web" / ".env"
    issues = check_env_database_url(env_path) + check_git_staged(repo)
    if not issues:
        print("OK — aislamiento local: sin DATABASE_URL local y sin .env/*.db en staging.")
        return 0
    print(WARN_HEADER)
    print("La base local (SQLite) y la remota (Postgres) no se sincronizan.")
    print("Riesgos detectados:")
    for item in issues:
        print(f"  - {item}")
    print("Acción segura: quitá DATABASE_URL del .env local; desestagiá .env e instance/*.db.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
