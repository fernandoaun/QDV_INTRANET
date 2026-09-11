from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECK = REPO / "openclaw" / "scripts" / "check_setup.py"


def _run(env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        [sys.executable, str(CHECK)],
        cwd=str(cwd or REPO / "openclaw"),
        env=merged,
        capture_output=True,
        text=True,
    )


def test_check_setup_refuses_database_url(tmp_path):
    (tmp_path / ".env.example").write_text("OPENCLAW_GATEWAY_TOKEN=x\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "OPENCLAW_GATEWAY_TOKEN=un-token-largo-de-prueba\n"
        "QDV_API_BEARER_TOKEN=otro-token-largo-de-prueba\n"
        "QDV_API_BASE_URL=http://127.0.0.1:5000\n"
        "QDV_WHATSAPP_ALLOW_FROM=+5491100000000\n"
        "DATABASE_URL=postgresql://user:pass@host/db\n",
        encoding="utf-8",
    )
    r = _run({"OPENCLAW_ROOT": str(tmp_path)})
    assert r.returncode == 2, r.stdout + r.stderr
    assert "aislamiento" in r.stdout


def test_check_setup_missing_env(tmp_path):
    (tmp_path / ".env.example").write_text("OPENCLAW_GATEWAY_TOKEN=x\n", encoding="utf-8")
    r = _run({"OPENCLAW_ROOT": str(tmp_path)})
    assert r.returncode == 1, r.stdout + r.stderr
    assert "Falta" in r.stdout


def test_qdv_skill_files_exist():
    skill = REPO / "openclaw" / "workspace" / "skills" / "qdv-planta" / "SKILL.md"
    helper = REPO / "openclaw" / "workspace" / "skills" / "qdv-planta" / "scripts" / "qdv-api.mjs"
    assert skill.is_file()
    skill_text = skill.read_text(encoding="utf-8")
    assert "qdv-planta" in skill_text
    assert "--from" in skill_text
    assert "sí, guardá" in skill_text
    assert helper.is_file()
    text = helper.read_text(encoding="utf-8")
    assert "/api/v1/stock/alertas" in text
    assert "X-QDV-WhatsApp" in text
    assert "DATABASE_URL" not in text or "no" in text.lower()
    yaml_text = (REPO / "render.yaml").read_text(encoding="utf-8")
    assert "healthCheckPath: /healthz" in yaml_text
    entry = (REPO / "openclaw" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "--port" in entry
    cfg = (REPO / "openclaw" / "scripts" / "ensure_config.mjs").read_text(encoding="utf-8")
    assert "plugins.entries.whatsapp" in cfg or "enableWhatsappPlugin" in cfg
