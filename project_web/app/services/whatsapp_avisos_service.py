"""
Copia por WhatsApp de los avisos que el sistema manda por mail.

`mail_service.enviar_mail` encola un mensaje por cada destinatario con legajo activo y celular;
el gateway de WhatsApp (OpenClaw) los retira por la API (`/api/v1/whatsapp/avisos`) y los envía.
Destinatarios sin legajo (direcciones externas) quedan solo con el mail.
"""
from __future__ import annotations

import html
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select, update

from app.extensions import db
from app.models import EmpleadoPersonal, User, WhatsappAviso
from app.services.whatsapp_identity import normalize_whatsapp_e164

log = logging.getLogger(__name__)

TEXTO_MAX = 3000
INTENTOS_MAX = 5
VIGENCIA = timedelta(hours=24)
ADJUNTOS_DIR = "whatsapp_adjuntos"
ADJUNTO_MAX_BYTES = 15 * 1024 * 1024
# (nombre visible, contenido, tipo MIME)
Adjunto = tuple[str, bytes, str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def telefonos_por_email(emails: list[str]) -> dict[str, str]:
    """email (minúsculas) → celular E.164: el WhatsApp del usuario o, si no tiene, el teléfono del legajo."""
    buscados = {(e or "").strip().lower() for e in emails if (e or "").strip()}
    if not buscados:
        return {}
    out: dict[str, str] = {}
    empleados = db.session.scalars(
        select(EmpleadoPersonal).where(func.lower(func.trim(EmpleadoPersonal.email)).in_(buscados))
    ).all()
    for emp in empleados:
        if (emp.estado or "activo") != "activo":
            continue
        e164 = None
        if emp.user_id:
            user = db.session.get(User, int(emp.user_id))
            if user is not None and user.activo:
                e164 = normalize_whatsapp_e164(user.whatsapp_e164)
        e164 = e164 or normalize_whatsapp_e164(emp.telefono)
        if e164:
            out[(emp.email or "").strip().lower()] = e164
    return out


_TAG = re.compile(r"<[^>]+>")


def armar_texto(asunto: str, cuerpo: str) -> str:
    asunto = (asunto or "").strip()
    cuerpo = html.unescape(_TAG.sub("", cuerpo or ""))  # restos de HTML de mails sin versión texto
    lineas = [ln.rstrip() for ln in (cuerpo or "").replace("\r\n", "\n").split("\n")]
    # Sin tiras de líneas vacías que deja la conversión desde HTML.
    limpio: list[str] = []
    for ln in lineas:
        if not ln.strip() and (not limpio or not limpio[-1].strip()):
            continue
        limpio.append(ln)
    texto = "\n".join(limpio).strip()
    if asunto:
        texto = f"*{asunto}*\n\n{texto}" if texto else f"*{asunto}*"
    if len(texto) > TEXTO_MAX:
        texto = texto[: TEXTO_MAX - 40].rstrip() + "\n\n… (sigue en el mail)"
    return texto


def _guardar_adjunto(adjunto: Adjunto) -> tuple[str, str]:
    """Guarda el archivo en uploads y devuelve (ruta relativa, nombre). Borra adjuntos de más de 3 días."""
    from app.services.upload_paths import uploads_workspace_root

    nombre, contenido, _mime = adjunto
    carpeta = uploads_workspace_root() / ADJUNTOS_DIR
    carpeta.mkdir(parents=True, exist_ok=True)
    limite = _utc_now().timestamp() - 3 * 86400
    for viejo in carpeta.iterdir():
        try:
            if viejo.is_file() and viejo.stat().st_mtime < limite:
                viejo.unlink()
        except OSError:
            pass
    ext = Path(nombre).suffix.lower()[:10] or ".bin"
    archivo = carpeta / f"{uuid.uuid4().hex}{ext}"
    archivo.write_bytes(contenido)
    return f"{ADJUNTOS_DIR}/{archivo.name}", (nombre or archivo.name)[:160]


def encolar_desde_mail(app: Any, emails: list[str], asunto: str, cuerpo: str, adjunto: Adjunto | None = None) -> int:
    """Encola la copia por WhatsApp de un mail ya enviado. Nunca levanta excepción (el mail ya salió)."""
    try:
        if not app.config.get("WHATSAPP_AVISOS_ENABLED", True):
            return 0
        with app.app_context():
            telefonos = sorted(set(telefonos_por_email(emails).values()))
            if not telefonos:
                return 0
            texto = armar_texto(asunto, cuerpo)
            adjunto_path, adjunto_nombre = "", ""
            if adjunto is not None and 0 < len(adjunto[1]) <= ADJUNTO_MAX_BYTES:
                adjunto_path, adjunto_nombre = _guardar_adjunto(adjunto)
            ahora = _utc_now()
            # Transacción propia: no confirma ni descarta lo que tenga pendiente la sesión del llamador.
            with db.engine.begin() as conn:
                conn.execute(
                    insert(WhatsappAviso),
                    [
                        {"telefono_e164": t, "texto": texto, "creado_en": ahora,
                         "adjunto_path": adjunto_path, "adjunto_nombre": adjunto_nombre}
                        for t in telefonos
                    ],
                )
            return len(telefonos)
    except Exception:
        log.exception("No se pudo encolar el aviso por WhatsApp (%s)", asunto)
        return 0


def pendientes(limit: int = 20) -> list[dict[str, Any]]:
    desde = _utc_now() - VIGENCIA
    rows = db.session.scalars(
        select(WhatsappAviso)
        .where(
            WhatsappAviso.enviado_en.is_(None),
            WhatsappAviso.intentos < INTENTOS_MAX,
            WhatsappAviso.creado_en >= desde,
        )
        .order_by(WhatsappAviso.id)
        .limit(max(1, min(int(limit), 100)))
    ).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        item: dict[str, Any] = {"id": r.id, "telefono": r.telefono_e164, "texto": r.texto}
        if r.adjunto_path:
            item["adjunto"] = {"nombre": r.adjunto_nombre, "url": f"/api/v1/whatsapp/avisos/{r.id}/adjunto"}
        out.append(item)
    return out


def adjunto_de_aviso(aviso_id: int) -> tuple[Path, str] | None:
    """(archivo, nombre) del adjunto de un aviso, si existe."""
    from app.services.upload_paths import uploads_workspace_root

    r = db.session.get(WhatsappAviso, int(aviso_id))
    if r is None or not r.adjunto_path:
        return None
    raiz = (uploads_workspace_root() / ADJUNTOS_DIR).resolve()
    f = (uploads_workspace_root() / r.adjunto_path).resolve()
    if f.parent != raiz or not f.is_file():
        return None
    return f, (r.adjunto_nombre or f.name)


def registrar_resultado(aviso_id: int, ok: bool, error: str = "") -> bool:
    valores: dict[str, Any] = {"intentos": WhatsappAviso.intentos + 1}
    if ok:
        valores["enviado_en"] = _utc_now()
        valores["ultimo_error"] = ""
    else:
        valores["ultimo_error"] = (error or "error")[:500]
    res = db.session.execute(
        update(WhatsappAviso)
        .where(WhatsappAviso.id == int(aviso_id), WhatsappAviso.enviado_en.is_(None))
        .values(**valores)
    )
    db.session.commit()
    return bool(res.rowcount)
