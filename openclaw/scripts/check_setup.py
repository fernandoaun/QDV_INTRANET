#!/usr/bin/env python3
"""Valida el setup de OpenClaw + QDV sin tocar bases de datos.

Exit 2: DATABASE_URL presente (aislamiento).
Exit 1: faltan archivos o valores placeholder.
Exit 0: listo o solo avisos.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("OPENCLAW_ROOT") or Path(__file__).resolve().parents[1])
ENV_PATH = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"
PLACEHOLDERS = {
    "OPENCLAW_GATEWAY_TOKEN": {"cambiá-este-valor", "cambia-este-valor", ""},
    "QDV_API_BEARER_TOKEN": {"cambiá-este-token", "cambia-este-token", ""},
}


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not EXAMPLE.is_file():
        print("ERROR: falta openclaw/.env.example")
        return 1

    if not ENV_PATH.is_file():
        print("Falta openclaw/.env")
        print("Acción: copy .env.example .env  (o ejecutá iniciar_openclaw.bat)")
        return 1

    env = parse_env(ENV_PATH)
    if (env.get("DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip():
        print("ADVERTENCIA — aislamiento de base local")
        print("La base local (SQLite) y la remota (Postgres) no se sincronizan.")
        print("Riesgo detectado: DATABASE_URL está definido en OpenClaw.")
        print("Acción segura: borralo. OpenClaw habla con QDV solo por /api/v1.")
        return 2

    for key, bad in PLACEHOLDERS.items():
        val = (env.get(key) or "").strip()
        if val.lower() in {b.lower() for b in bad} or len(val) < 12:
            errors.append(f"{key} no está definido (sigue el placeholder o es demasiado corto).")

    allow = (env.get("QDV_WHATSAPP_ALLOW_FROM") or "").strip()
    if not allow or allow.startswith("+54911XXXX"):
        warnings.append("QDV_WHATSAPP_ALLOW_FROM: cargá números reales E.164 (ej. +54911...).")
    elif not allow.startswith("+"):
        errors.append("QDV_WHATSAPP_ALLOW_FROM debe ir en E.164 (empieza con +).")

    base = (env.get("QDV_API_BASE_URL") or "").rstrip("/")
    if not base:
        errors.append("QDV_API_BASE_URL vacío.")
    elif "onrender.com" not in base and "host.docker.internal" not in base and "127.0.0.1" not in base and "localhost" not in base:
        warnings.append(f"QDV_API_BASE_URL={base} — confirmá que sea la URL HTTPS de QDV o host.docker.internal:5000.")

    has_model = any((env.get(k) or "").strip() for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"))
    if not has_model:
        warnings.append("No hay clave de modelo en .env. Cargala acá o en el dashboard de OpenClaw.")

    if errors:
        print("Errores:")
        for e in errors:
            print(f"  - {e}")
        print("Acción: editá openclaw/.env (valores reales, sin DATABASE_URL).")
        return 1

    for w in warnings:
        print(f"Aviso: {w}")

    token = env.get("QDV_API_BEARER_TOKEN") or ""
    if base:
        try:
            req = urllib.request.Request(f"{base}/api/v1/health", method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            print(f"QDV health OK ({base}/api/v1/health)")
            if "qdv_web" not in body:
                warnings.append("health respondió pero no parece QDV.")
        except urllib.error.HTTPError as exc:
            print(f"Aviso: QDV health HTTP {exc.code} en {base} (¿está levantada la web?)")
        except Exception as exc:
            print(f"Aviso: no pude contactar QDV ({base}): {exc}")
        else:
            if token and not token.lower().startswith("cambiá"):
                from_num = ""
                for part in allow.replace(";", ",").split(","):
                    p = part.strip()
                    if p.startswith("+") and "X" not in p.upper():
                        from_num = p
                        break
                headers = {"Authorization": f"Bearer {token}"}
                path = "/api/v1/dashboard/snapshot"
                if from_num:
                    headers["X-QDV-WhatsApp"] = from_num
                    path = "/api/v1/me"
                try:
                    req = urllib.request.Request(
                        f"{base}{path}",
                        headers=headers,
                        method="GET",
                    )
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        print(f"QDV Bearer OK ({path} HTTP {resp.status})")
                except urllib.error.HTTPError as exc:
                    if exc.code == 403 and from_num:
                        print(
                            f"Aviso: {path} HTTP 403. El número {from_num} no está "
                            "vinculado a un usuario QDV activo (Admin → Usuarios → WhatsApp)."
                        )
                    else:
                        print(
                            f"Aviso: Bearer {path} HTTP {exc.code}. "
                            "Revisá API_BEARER_TOKEN y X-QDV-WhatsApp / usuario QDV."
                        )
                except Exception as exc:
                    print(f"Aviso: Bearer no se pudo probar: {exc}")

    print("Check OpenClaw: OK")
    print("Siguiente: docker compose up --build   y después whatsapp_login.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
