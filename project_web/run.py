from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    # 127.0.0.1 = solo tu PC (menos problemas con firewall). Para abrir desde el celular en la misma WiFi: HOST=0.0.0.0
    host = (os.environ.get("HOST") or "127.0.0.1").strip()
    url = f"http://127.0.0.1:{port}/"
    print()
    print("=" * 60)
    print("  QDV WEB — Dejá esta ventana ABIERTA mientras usás el navegador.")
    print(f"  Abrí en el navegador: {url}")
    print()
    print("  NO hay usuario ni contraseña por defecto.")
    print("  Primera vez: abrí OTRA ventana de PowerShell, en project_web ejecutá:")
    print('    python -m flask --app run create-admin admin --password "ElegiTuClave123"')
    print("  (Podés cambiar admin por el nombre de usuario que quieras.)")
    print("=" * 60)
    print()
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False))
