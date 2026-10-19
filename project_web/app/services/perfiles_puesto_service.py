"""Perfiles de puesto (registro SGI QDV-RG-PG-05_01): un perfil por puesto del organigrama, editable."""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import PerfilPuesto, PerfilPuestoCambio
from app.services.fichas_proceso_service import fecha_local, items
from app.utils.datetime_operacion import now_operacion_naive_local

REGISTRO = {
    "codigo": "QDV-RG-PG-05_01",
    "titulo": "PERFIL DE PUESTO",
    "fecha_vigencia": date(2026, 6, 24),
    "revision": "00",
}

# Datos de una línea (encabezado del perfil).
CAMPOS_TEXTO: tuple[str, ...] = ("puesto", "proceso", "supervisor", "aprobado_por")
# Listas: un ítem por renglón.
LISTAS: tuple[str, ...] = (
    "supervisa_a",
    "interactua_con",
    "tareas",
    "educacion",
    "formacion",
    "idiomas_otros",
    "experiencia",
    "habilidades",
    "autoridad",
    "rendicion_cuentas",
)
CAMPO_LABELS: dict[str, str] = {
    "puesto": "Denominación del cargo",
    "proceso": "Proceso",
    "supervisor": "Supervisor inmediato / directo",
    "supervisa_a": "Supervisa a",
    "interactua_con": "Interactúa principalmente con",
    "tareas": "Principales tareas y responsabilidades",
    "educacion": "Educación requerida",
    "formacion": "Formación requerida",
    "idiomas_otros": "Idiomas y otros",
    "experiencia": "Experiencia previa",
    "habilidades": "Competencias aptitudinales – Habilidades",
    "autoridad": "Posee autoridad para",
    "rendicion_cuentas": "Rendición de cuentas",
    "aprobado_por": "Aprobado por",
    "alta": "Alta",
    "baja": "Baja",
}


def _today() -> date:
    return now_operacion_naive_local().date()


def _unir(lista: list[str]) -> str:
    return "\n".join(x.strip() for x in lista if x and x.strip())


def labels_context() -> dict[str, Any]:
    return {"reg": REGISTRO, "items": items, "perfil_campo_labels": CAMPO_LABELS, "fecha_local": fecha_local}


def listar() -> list[PerfilPuesto]:
    return list(
        db.session.scalars(
            select(PerfilPuesto).where(PerfilPuesto.activo.is_(True)).order_by(PerfilPuesto.orden, PerfilPuesto.puesto)
        )
    )


def get(perfil_id: int) -> PerfilPuesto | None:
    p = db.session.get(PerfilPuesto, int(perfil_id))
    return p if p is not None and p.activo else None


def cambios(perfil: PerfilPuesto, limit: int = 100) -> list[PerfilPuestoCambio]:
    return list(
        db.session.scalars(
            select(PerfilPuestoCambio)
            .where(PerfilPuestoCambio.perfil_id == perfil.id)
            .order_by(PerfilPuestoCambio.created_at.desc(), PerfilPuestoCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(perfil: PerfilPuesto, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        PerfilPuestoCambio(
            perfil_id=perfil.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes is None else str(antes),
            despues=None if despues is None else str(despues),
        )
    )


def _limpio(data: Any) -> tuple[dict[str, str], list[str]]:
    v = {k: (data.get(k) or "").strip()[:160] for k in CAMPOS_TEXTO}
    for k in LISTAS:
        raw = data.get(k)
        v[k] = _unir(raw if isinstance(raw, list) else items(raw))
    errores = [] if v["puesto"] else ["La denominación del cargo es obligatoria."]
    return v, errores


def guardar(perfil: PerfilPuesto, data: Any, user_id: int | None) -> list[str]:
    v, errores = _limpio(data)
    if errores:
        return errores
    hubo = False
    for campo, nuevo in v.items():
        antes = getattr(perfil, campo) or ""
        if antes == nuevo:
            continue
        setattr(perfil, campo, nuevo)
        _log(perfil, user_id, campo, antes, nuevo)
        hubo = True
    if hubo:
        perfil.fecha_actualizacion = _today()
    return []


def crear(data: Any, user_id: int | None, fecha_actualizacion: date | None = None) -> tuple[PerfilPuesto | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    orden = (db.session.scalar(select(func.max(PerfilPuesto.orden))) or 0) + 1
    perfil = PerfilPuesto(orden=orden, fecha_actualizacion=fecha_actualizacion or _today(), **v)
    db.session.add(perfil)
    db.session.flush()
    _log(perfil, user_id, "alta", None, perfil.puesto)
    return perfil, []


def baja(perfil: PerfilPuesto, user_id: int | None) -> None:
    perfil.activo = False
    _log(perfil, user_id, "baja", perfil.puesto, None)


# ---------------------------------------------------------------- lectura del perfil en Word (.doc)

# Rótulo de la celda en la plantilla (normalizado) → campo.
_ROTULOS: dict[str, str] = {
    "denominacion del cargo": "puesto",
    "proceso": "proceso",
    "supervisor inmediato / directo": "supervisor",
    "supervisa a": "supervisa_a",
    "interactua principalmente con": "interactua_con",
    "principales tareas y responsabilidades": "tareas",
    "educacion requerida": "educacion",
    "formacion requerida": "formacion",
    "idiomas y otros": "idiomas_otros",
    "experiencia previa": "experiencia",
    "competencias aptitudinales - habilidades": "habilidades",
    "competencias aptitudinales habilidades": "habilidades",
    "posee autoridad para": "autoridad",
    "rendicion de cuentas": "rendicion_cuentas",
}
# Títulos de sección y subtítulos que no llevan valor propio.
_SIN_VALOR = {"informacion principal", "descripcion del cargo", "competencias", "competencias cognitivas", "competencias funcionales"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.replace("–", "-").replace("—", "-"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().rstrip(":").strip().lower()


def _renglones(celda: str) -> list[str]:
    return [re.sub(r"\s+", " ", x).strip() for x in re.split(r"[\r\n\x0b]", celda) if x.strip()]


def leer_doc(contenido: bytes) -> tuple[dict[str, Any] | None, str | None]:
    """Extrae un perfil de la plantilla Word 97 (.doc) del registro: tabla de rótulo → valor."""
    texto = contenido.decode("cp1252", "ignore")
    ini = texto.find("INFORMACIÓN PRINCIPAL")
    if ini < 0:
        return None, "No encontré «INFORMACIÓN PRINCIPAL»: tiene que ser el perfil de puesto en Word (.doc)."
    fin = texto.find("Control de Cambios", ini)
    celdas = texto[ini : fin if fin > 0 else None].split("\x07")
    data: dict[str, Any] = {k: "" for k in CAMPOS_TEXTO}
    data.update({k: [] for k in LISTAS})
    pendiente: str | None = None
    for celda in celdas:
        lineas = _renglones(celda)
        if not lineas:
            continue
        clave = _norm(" ".join(lineas))
        if clave in _ROTULOS:
            pendiente = _ROTULOS[clave]
            continue
        if clave in _SIN_VALOR:
            pendiente = None
            continue
        if any(ln.lower().startswith("fecha de actualización") for ln in lineas):
            for ln in lineas:
                m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", ln)
                if ln.lower().startswith("fecha de actualización") and m:
                    data["fecha_actualizacion"] = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                elif ln.lower().startswith("aprobado por"):
                    data["aprobado_por"] = ln.split(":", 1)[-1].strip()
            pendiente = None
            continue
        if pendiente is None:
            continue
        if pendiente in CAMPOS_TEXTO:
            data[pendiente] = " ".join(lineas)
        else:
            data[pendiente] = lineas
        pendiente = None
    if not data["puesto"]:
        return None, "No encontré la denominación del cargo en el perfil."
    return data, None
