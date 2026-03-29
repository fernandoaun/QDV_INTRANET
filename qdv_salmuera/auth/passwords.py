from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Optional

# Iteraciones PBKDF2-HMAC-SHA256 (recomendación OWASP ~2023 para este algoritmo)
_PBKDF2_ITERATIONS = 310_000


def hash_password(plain: str) -> str:
    """Devuelve cadena almacenable: pbkdf2_sha256$iter$salt_hex$hash_b64"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        plain.encode("utf-8"),
        salt.encode("ascii"),
        _PBKDF2_ITERATIONS,
    )
    hb = base64.b64encode(dk).decode("ascii")
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${hb}"


def verify_password(stored: str, plain: str) -> bool:
    if not stored or not plain:
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = parts[2]
        expected_b64 = parts[3]
    except (ValueError, IndexError):
        return False
    try:
        expected = base64.b64decode(expected_b64.encode("ascii"))
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        plain.encode("utf-8"),
        salt.encode("ascii"),
        iterations,
    )
    return hmac.compare_digest(dk, expected)
