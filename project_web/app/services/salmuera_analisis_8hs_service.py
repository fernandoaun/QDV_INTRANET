from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import SalmueraAnalisis8hs
from app.web.modules.produccion.operativa_context import compute_turno_from_hour

ANALISIS_8HS_INTERVAL_SECONDS = 8 * 60 * 60


def _parse_float_required(raw: str | None, label: str) -> float:
    s = (raw or "").strip().replace(",", ".")
    if not s:
        raise ValueError(f"{label} es obligatorio.")
    try:
        v = float(s)
    except ValueError as exc:
        raise ValueError(f"{label} debe ser numérico.") from exc
    if v != v:
        raise ValueError(f"{label} debe ser numérico.")
    return v


def row_to_dict(row: SalmueraAnalisis8hs) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "fecha": row.fecha,
        "hora": row.hora,
        "fecha_hora_iso": row.fecha_hora_iso,
        "turno": row.turno,
        "operador": row.operador,
        "dureza_salmuera": float(row.dureza_salmuera),
        "cloro_libre_salmuera": float(row.cloro_libre_salmuera),
        "observaciones": row.observaciones or "",
        "created_at_iso": row.created_at_iso,
    }


def create_from_form(form: Any, *, now: datetime, operador: str) -> SalmueraAnalisis8hs:
    dureza = _parse_float_required(form.get("dureza_salmuera"), "Dureza de salmuera")
    cloro = _parse_float_required(form.get("cloro_libre_salmuera"), "Cloro libre en salmuera")
    fecha = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M")
    iso = now.isoformat(timespec="seconds")
    row = SalmueraAnalisis8hs(
        fecha=fecha,
        hora=hora,
        fecha_hora_iso=iso,
        turno=compute_turno_from_hour(hora),
        operador=(operador or "").strip(),
        dureza_salmuera=dureza,
        cloro_libre_salmuera=cloro,
        observaciones=(form.get("observaciones") or "").strip() or None,
        created_at_iso=iso,
    )
    db.session.add(row)
    db.session.flush()
    return row


def latest_row() -> SalmueraAnalisis8hs | None:
    return db.session.scalar(
        select(SalmueraAnalisis8hs).order_by(SalmueraAnalisis8hs.fecha_hora_iso.desc(), SalmueraAnalisis8hs.id.desc()).limit(1)
    )


def build_status(now: datetime) -> dict[str, Any]:
    row = latest_row()
    if row is None:
        return {
            "has_records": False,
            "last": None,
            "next_due_iso": None,
            "remaining_seconds": None,
            "is_due": True,
            "message": "No hay análisis registrados. Realizar primer análisis.",
        }
    try:
        last_dt = datetime.fromisoformat(str(row.fecha_hora_iso))
    except ValueError:
        last_dt = now
    next_due = last_dt + timedelta(seconds=ANALISIS_8HS_INTERVAL_SECONDS)
    remaining = int((next_due - now).total_seconds())
    return {
        "has_records": True,
        "last": row_to_dict(row),
        "next_due_iso": next_due.isoformat(timespec="seconds"),
        "remaining_seconds": remaining,
        "is_due": remaining <= 0,
        "message": (
            "Análisis de salmuera vencido. Registrar dureza y cloro libre."
            if remaining <= 0
            else "Próximo análisis programado."
        ),
    }


def filtered_rows(fecha_desde: str = "", fecha_hasta: str = "", *, limit: int | None = 1000) -> list[SalmueraAnalisis8hs]:
    desde = (fecha_desde or "").strip()
    hasta = (fecha_hasta or "").strip()
    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde
    q = select(SalmueraAnalisis8hs)
    if desde:
        q = q.where(SalmueraAnalisis8hs.fecha >= desde)
    if hasta:
        q = q.where(SalmueraAnalisis8hs.fecha <= hasta)
    q = q.order_by(SalmueraAnalisis8hs.fecha_hora_iso.desc(), SalmueraAnalisis8hs.id.desc())
    if limit is not None:
        q = q.limit(int(limit))
    return list(db.session.scalars(q).all())


def export_excel(fecha_desde: str = "", fecha_hasta: str = "") -> BytesIO:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    headers = [
        "Fecha",
        "Hora",
        "Turno",
        "Operador",
        "Dureza de salmuera",
        "Cloro libre en salmuera",
        "Observaciones",
        "Fecha/hora ISO",
        "Creado",
    ]
    rows = filtered_rows(fecha_desde, fecha_hasta, limit=None)
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Analisis salmuera 8hs"
    bold = Font(bold=True)
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = bold
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    for r_idx, row in enumerate(rows, start=2):
        values = [
            row.fecha,
            row.hora,
            row.turno,
            row.operador,
            float(row.dureza_salmuera),
            float(row.cloro_libre_salmuera),
            row.observaciones or "",
            row.fecha_hora_iso,
            row.created_at_iso,
        ]
        for c_idx, value in enumerate(values, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value).alignment = Alignment(vertical="top", wrap_text=False)
    max_row = 1 + len(rows)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max_row}"
    for c_idx in range(1, len(headers) + 1):
        letter = get_column_letter(c_idx)
        max_len = 10
        for r_idx in range(1, min(max_row, 500) + 1):
            v = ws.cell(row=r_idx, column=c_idx).value
            if v is not None:
                max_len = max(max_len, min(len(str(v)), 60))
        ws.column_dimensions[letter].width = min(max_len + 2, 55)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
