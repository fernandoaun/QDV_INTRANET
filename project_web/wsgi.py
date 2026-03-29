"""
Punto de entrada WSGI para gunicorn: `gunicorn wsgi:app`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app

app = create_app()
