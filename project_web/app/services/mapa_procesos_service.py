"""Mapa de procesos (registro SGI QDV-RG-PG-09_02): el diagrama aprobado, con cada proceso enlazado a su ficha."""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import FichaProceso
from app.services.plan_accion_service import fecha_dmy

REGISTRO = {
    "codigo": "QDV-RG-PG-09_02",
    "titulo": "MAPA DE PROCESOS",
    "subtitulo": "QUÍMICA DEL VALLE S.R.L.",
    "fecha_vigencia": date(2026, 5, 12),
    "fecha_actualizacion": date(2026, 5, 20),
    "revision": "00",
}
# Cada proceso: (nombre en el mapa, icono, nombre de su ficha de proceso QDV-RG-PG-09_03).
ESTRATEGICOS = (("Gerencia", "bi-people-fill", "Gerencia"), ("Sistema de gestión de la calidad", "bi-patch-check-fill", "SGC"))
DISENO = ("Diseño y desarrollo", "bi-pencil-square", "Diseño y desarrollo")
PRODUCCION = ("Producción", "bi-gear-wide-connected", "Producción")
DESPACHO = ("Despacho y distribución", "bi-truck", "Despacho y distribución")
CONTROL = ("Control de calidad", "bi-clipboard2-check", "Control de calidad")
APOYO = (
    ("RRHH", "bi-people", "RRHH"),
    ("Administración", "bi-calculator", "Administración"),
    ("Mantenimiento", "bi-tools", "Mantenimiento"),
    ("Compras y proveedores", "bi-cart3", "Compras y proveedores"),
    ("HSE", "bi-shield-check", "HSE"),
)
ETAPAS_PRODUCCION = (
    "Saturación de salmuera", "Clarificación y precipitación", "Filtrado", "Intercambio iónico", "Electrólisis",
    "Formación de hipoclorito", "Almacenamiento",
)
ETAPAS_EFLUENTES = ("Reductor de clorato", "Declorinación primaria", "Declorinación secundaria")
ENTRADAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Requerimientos de:", ("Clientes", "Proveedores", "Otras partes interesadas")),
    ("Requisitos legales y otros", ()),
    ("Materia prima e insumos:", (
        "Cloruro de sodio", "Hidróxido de sodio", "Ácido clorhídrico", "Carbonato de sodio", "Metabisulfito de sodio", "Agua",
        "Energía eléctrica",
    )),
)
SALIDAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Satisfacción del cliente", ()),
    ("Productos:", ("Hipoclorito de sodio", "Agua lavandina")),
    ("Residuos / efluentes tratados conforme a requisitos legales", ()),
)


def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", x).strip()


def fichas() -> dict[str, int]:
    """Nombre normalizado del proceso → id de su ficha activa."""
    return {
        _norm(f.proceso): f.id
        for f in db.session.scalars(select(FichaProceso).where(FichaProceso.activo.is_(True)))
    }


def contexto() -> dict[str, Any]:
    ids = fichas()
    return {
        "reg": REGISTRO, "estrategicos": ESTRATEGICOS, "diseno": DISENO, "produccion": PRODUCCION, "despacho": DESPACHO,
        "control": CONTROL, "apoyo": APOYO, "etapas_produccion": ETAPAS_PRODUCCION, "etapas_efluentes": ETAPAS_EFLUENTES,
        "entradas": ENTRADAS, "salidas": SALIDAS, "fecha_dmy": fecha_dmy,
        "ficha_id": lambda proceso: ids.get(_norm(proceso[2])),
    }
