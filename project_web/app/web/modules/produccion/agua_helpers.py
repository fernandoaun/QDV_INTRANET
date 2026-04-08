"""Lógica auxiliar del circuito de agua y columnas de intercambio."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Response, redirect, request, url_for
from sqlalchemy import func, select

from app.extensions import db
from app.models import AguaRegistro, ColumnaIntercambio
from app.services.operational_warnings import warnings_for_agua_registro
from app.web.modules.produccion.operativa_context import now_local

COLUMNA_INTERCAMBIO_ESTADOS = frozenset({"En operación", "Regenerada", "Por Regenerar"})


def next_agua_lote(fecha_iso: str) -> str:
    n = db.session.scalar(
        select(func.count()).select_from(AguaRegistro).where(AguaRegistro.fecha_iso == fecha_iso)
    )
    correlative = int(n or 0) + 1
    dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
    return f"{dt.strftime('%y%m%d')}{correlative:02d}"


def last_agua_created_at_iso_for_date(fecha_iso: str) -> str | None:
    return db.session.scalar(
        select(AguaRegistro.created_at_iso)
        .where(AguaRegistro.fecha_iso == fecha_iso)
        .order_by(AguaRegistro.id.desc())
        .limit(1)
    )


def agua_row_to_dict(r: AguaRegistro) -> dict[str, Any]:
    return {
        "id": r.id,
        "fecha_iso": r.fecha_iso,
        "hora_hm": r.hora_hm,
        "turno": r.turno,
        "operador": r.operador,
        "lote": r.lote,
        "numero_columna": r.numero_columna,
        "temperatura": r.temperatura,
        "dureza": r.dureza,
        "observaciones": r.observaciones or "",
        "created_at_iso": r.created_at_iso,
        "warnings": warnings_for_agua_registro(r),
    }


def columnas_latest_dict() -> dict[int, dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for col in (1, 2, 3):
        r = db.session.scalars(
            select(ColumnaIntercambio)
            .where(ColumnaIntercambio.columna_numero == col)
            .order_by(ColumnaIntercambio.id.desc())
            .limit(1)
        ).first()
        if r:
            latest[col] = {
                "estado": r.estado,
                "fecha_regeneracion": r.fecha_regeneracion or "",
                "hora_regeneracion": r.hora_regeneracion or "",
                "dureza_salida_ppm": r.dureza_salida_ppm,
                "dureza_post_regeneracion_ppm": r.dureza_post_regeneracion_ppm,
                "observaciones": r.observaciones or "",
            }
        else:
            latest[col] = {
                "estado": "En operación",
                "fecha_regeneracion": "",
                "hora_regeneracion": "",
                "dureza_salida_ppm": None,
                "dureza_post_regeneracion_ppm": None,
                "observaciones": "",
            }
    return latest


def columnas_semaforo_global(latest: dict[int, dict[str, Any]]) -> dict[str, str]:
    estados = [(latest.get(col) or {}).get("estado", "En operación") for col in (1, 2, 3)]
    if any(s == "Por Regenerar" for s in estados):
        return {"nivel": "rojo", "texto": "Requiere regeneración"}
    if any(s == "Regenerada" for s in estados):
        return {"nivel": "amarillo", "texto": "Columnas regeneradas"}
    return {"nivel": "verde", "texto": "Sistema en operación"}


def save_columna_intercambio_from_form() -> None:
    now = now_local()
    now_iso = now.isoformat(timespec="seconds")
    col = int(request.form.get("columna_numero") or 1)
    estado = (request.form.get("estado") or "").strip()
    if estado not in COLUMNA_INTERCAMBIO_ESTADOS:
        raise ValueError("Estado de columna no válido.")
    fr = now.strftime("%d/%m/%Y")
    hr = now.strftime("%H:%M")
    dsp = request.form.get("dureza_salida_ppm")
    dpp = request.form.get("dureza_post_regeneracion_ppm")
    db.session.add(
        ColumnaIntercambio(
            columna_numero=col,
            estado=estado,
            fecha_regeneracion=fr,
            hora_regeneracion=hr,
            dureza_salida_ppm=float(dsp.replace(",", ".")) if dsp else None,
            dureza_post_regeneracion_ppm=float(dpp.replace(",", ".")) if dpp else None,
            observaciones=(request.form.get("observaciones") or "").strip(),
            created_at_iso=now_iso,
            updated_at_iso=now_iso,
        )
    )


def redirect_agua_columnas_anchor(fecha: str) -> Response:
    return redirect(url_for("produccion.agua", fecha=fecha) + "#columnas")
