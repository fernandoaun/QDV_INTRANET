"""Fichas de proceso (registro SGI QDV-RG-PG-09_03): diagrama tortuga por proceso, editable."""
from __future__ import annotations

import re
import zipfile
from datetime import date, datetime, timezone
from typing import Any, BinaryIO
from xml.etree import ElementTree as ET

from sqlalchemy import func, select

from app.extensions import db
from app.models import FichaProceso, FichaProcesoCambio
from app.utils.datetime_operacion import now_operacion_naive_local

REGISTRO = {
    "codigo": "QDV-RG-PG-09_03",
    "titulo": "FICHA DE PROCESO",
    "fecha_vigencia": date(2026, 8, 4),
    "revision": "00",
}

# Cajas de la tortuga: clave del campo → título en la ficha.
CAJAS: dict[str, str] = {
    "con_que": "¿CON QUÉ?",
    "entradas": "ENTRADAS",
    "como": "¿CÓMO?",
    "con_quien": "¿CON QUIÉN?",
    "salidas": "SALIDAS",
    "indicadores": "INDICADORES",
}
LISTAS: tuple[str, ...] = ("actividades", *CAJAS)
CAMPO_LABELS: dict[str, str] = {
    "proceso": "Proceso",
    "responsable": "Responsable",
    "actividades": "Actividades",
    **{k: v.title() for k, v in CAJAS.items()},
    "alta": "Alta",
    "baja": "Baja",
}


def _today() -> date:
    return now_operacion_naive_local().date()


def items(texto: str | None) -> list[str]:
    return [ln.strip() for ln in (texto or "").splitlines() if ln.strip()]


def _unir(lista: list[str]) -> str:
    return "\n".join(x.strip() for x in lista if x and x.strip())


def fecha_local(dt: datetime | None) -> str:
    if dt is None:
        return ""
    from app.utils.datetime_operacion import operacion_zoneinfo

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(operacion_zoneinfo()).strftime("%d/%m/%Y %H:%M")


def labels_context() -> dict[str, Any]:
    return {"reg": REGISTRO, "cajas": CAJAS, "items": items, "ficha_campo_labels": CAMPO_LABELS, "fecha_local": fecha_local}


def listar() -> list[FichaProceso]:
    return list(
        db.session.scalars(
            select(FichaProceso).where(FichaProceso.activo.is_(True)).order_by(FichaProceso.orden, FichaProceso.proceso)
        )
    )


def get(ficha_id: int) -> FichaProceso | None:
    f = db.session.get(FichaProceso, int(ficha_id))
    return f if f is not None and f.activo else None


def cambios(ficha: FichaProceso, limit: int = 100) -> list[FichaProcesoCambio]:
    return list(
        db.session.scalars(
            select(FichaProcesoCambio)
            .where(FichaProcesoCambio.ficha_id == ficha.id)
            .order_by(FichaProcesoCambio.created_at.desc(), FichaProcesoCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(ficha: FichaProceso, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        FichaProcesoCambio(
            ficha_id=ficha.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes is None else str(antes),
            despues=None if despues is None else str(despues),
        )
    )


def _limpio(data: Any) -> tuple[dict[str, str], list[str]]:
    v = {
        "proceso": (data.get("proceso") or "").strip()[:160],
        "responsable": (data.get("responsable") or "").strip()[:160],
    }
    for k in LISTAS:
        raw = data.get(k)
        v[k] = _unir(raw if isinstance(raw, list) else items(raw))
    errores = [] if v["proceso"] else ["El nombre del proceso es obligatorio."]
    return v, errores


def guardar(ficha: FichaProceso, data: Any, user_id: int | None) -> list[str]:
    v, errores = _limpio(data)
    if errores:
        return errores
    hubo = False
    for campo, nuevo in v.items():
        antes = getattr(ficha, campo) or ""
        if antes == nuevo:
            continue
        setattr(ficha, campo, nuevo)
        _log(ficha, user_id, campo, antes, nuevo)
        hubo = True
    if hubo:
        ficha.fecha_actualizacion = _today()
    return []


def crear(data: Any, user_id: int | None, fecha_actualizacion: date | None = None) -> tuple[FichaProceso | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    orden = (db.session.scalar(select(func.max(FichaProceso.orden))) or 0) + 1
    ficha = FichaProceso(orden=orden, fecha_actualizacion=fecha_actualizacion or _today(), **v)
    db.session.add(ficha)
    db.session.flush()
    _log(ficha, user_id, "alta", None, ficha.proceso)
    return ficha, []


def baja(ficha: FichaProceso, user_id: int | None) -> None:
    ficha.activo = False
    _log(ficha, user_id, "baja", ficha.proceso, None)


# ---------------------------------------------------------------- lectura de la ficha en PowerPoint

_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_TITULOS = {v: k for k, v in CAJAS.items()}


def _parrafos(el: ET.Element) -> list[str]:
    out = []
    for p in el.iter(_A + "p"):
        t = re.sub(r"\s+", " ", "".join(x.text or "" for x in p.iter(_A + "t"))).strip()
        if t:
            out.append(t)
    return out


def leer_pptx(fh: BinaryIO) -> tuple[dict[str, Any] | None, str | None]:
    """Extrae una ficha de la plantilla PowerPoint del registro (tablas con título + recuadro del proceso)."""
    try:
        z = zipfile.ZipFile(fh)
        root = ET.fromstring(z.read("ppt/slides/slide1.xml"))
    except Exception:
        return None, "No se pudo leer el archivo: tiene que ser la ficha de proceso en PowerPoint (.pptx)."
    data: dict[str, Any] = {k: [] for k in LISTAS}
    fecha: date | None = None
    for tbl in root.iter(_A + "tbl"):
        filas = [_parrafos(tr) for tr in tbl.iter(_A + "tr")]
        if filas and filas[0] and filas[0][0].upper() in _TITULOS:
            data[_TITULOS[filas[0][0].upper()]] = [x for fila in filas[1:] for x in fila]
    for sp in root.iter(_P + "sp"):
        ps = _parrafos(sp)
        if not ps:
            continue
        if ps[0].startswith("Proceso "):
            data["proceso"] = ps[0][len("Proceso ") :].strip()
            resto = ps[1:]
            if resto and resto[0].lower().startswith("responsable"):
                data["responsable"] = resto[0].split(":", 1)[-1].strip()
                resto = resto[1:]
            data["actividades"] = resto
        elif ps[0].lower().startswith("fecha de actualización"):
            m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", " ".join(ps))
            if m:
                fecha = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    if not data.get("proceso"):
        return None, "No encontré el recuadro «Proceso …» en la ficha."
    data["fecha_actualizacion"] = fecha
    return data, None
