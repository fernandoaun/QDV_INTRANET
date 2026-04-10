from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, select

from app.extensions import db
from app.models import AguaRegistro, ColumnaIntercambio, ConsumoStock, Equipo, ReactorRegistro, SalmueraRegistro
from app.utils.datetime_operacion import format_consumo_stock_panel_datetime


def _fmt_ts(fecha_iso: str | None, hora_hm: str | None) -> str:
    f = (fecha_iso or "").strip()
    h = (hora_hm or "").strip()
    if f and h:
        return f"{f} {h}"
    return f or h or "-"


def ultimos_hipoclorito_por_rectificador(limit: int = 20) -> list[dict[str, Any]]:
    n = int(limit or 20)
    if n < 1:
        n = 1
    if n > 100:
        n = 100

    rank_col = func.row_number().over(
        partition_by=SalmueraRegistro.electrolizador,
        order_by=(SalmueraRegistro.created_at_iso.desc(), SalmueraRegistro.id.desc()),
    )
    ranked = (
        select(SalmueraRegistro.id.label("sid"), rank_col.label("rn"))
        .subquery()
    )
    rows = db.session.scalars(
        select(SalmueraRegistro)
        .join(ranked, ranked.c.sid == SalmueraRegistro.id)
        .where(ranked.c.rn == 1)
        .order_by(SalmueraRegistro.electrolizador.asc())
        .limit(n)
    ).all()

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "rectificador": r.electrolizador,
                "fecha_hora": _fmt_ts(r.fecha_iso, r.hora_hm),
                "turno": r.turno,
                "operador": r.operador,
                "lote": (r.lote or "").strip(),
                "cantidad_celdas": r.cantidad_celdas,
                "voltaje_total": r.voltaje_total,
                "amperaje": r.amperaje,
                "caudal_agua_l_h": r.caudal_agua_l_h,
                "caudal_salmuera_l_h": r.caudal_salmuera_l_h,
                "hipo_conc": r.hipo_conc,
                "hipo_exceso_soda": r.hipo_exceso_soda,
                "sal_temp": r.sal_temp,
                "sal_conc": r.sal_conc,
                "sal_ph": r.sal_ph,
                "soda_conc": r.soda_conc,
                "declor_ph": r.declor_ph,
                "observaciones": (r.observaciones or "").strip(),
            }
        )
    return out


def ultimo_registro_salmuera() -> dict[str, Any] | None:
    r = db.session.scalars(
        select(ReactorRegistro).order_by(ReactorRegistro.created_at_iso.desc(), ReactorRegistro.id.desc()).limit(1)
    ).first()
    if r is None:
        return None
    return {
        "fecha_hora": _fmt_ts(r.fecha_iso, r.hora_hm),
        "operador": r.operador,
        "lote": r.lote,
        "ph": r.ph,
        "temperatura": r.temperatura,
        "densidad": r.densidad,
        "concentracion_salmuera": r.concentracion_tabla,
        "exceso_soda": r.exceso_naoh,
        "exceso_carbonato_sodio": r.exceso_na2co3,
        "observaciones": (r.observaciones or "").strip(),
    }


def _latest_columnas_estado_text() -> str:
    rank_col = func.row_number().over(
        partition_by=ColumnaIntercambio.columna_numero,
        order_by=(ColumnaIntercambio.updated_at_iso.desc(), ColumnaIntercambio.id.desc()),
    )
    ranked = select(
        ColumnaIntercambio.columna_numero.label("columna_numero"),
        ColumnaIntercambio.estado.label("estado"),
        rank_col.label("rn"),
    ).subquery()
    rows = db.session.execute(
        select(ranked.c.columna_numero, ranked.c.estado)
        .where(ranked.c.rn == 1)
        .order_by(ranked.c.columna_numero.asc())
    ).all()
    if not rows:
        return ""
    return " | ".join([f"C{int(col)}: {str(est)}" for col, est in rows])


def ultimo_registro_agua() -> dict[str, Any] | None:
    r = db.session.scalars(
        select(AguaRegistro).order_by(AguaRegistro.created_at_iso.desc(), AguaRegistro.id.desc()).limit(1)
    ).first()
    if r is None:
        return None
    return {
        "fecha_hora": _fmt_ts(r.fecha_iso, r.hora_hm),
        "turno": r.turno,
        "operador": r.operador,
        "numero_columna": r.numero_columna,
        "dureza": r.dureza,
        "temperatura": r.temperatura,
        "estado_columnas": _latest_columnas_estado_text(),
        "observaciones": (r.observaciones or "").strip(),
    }


def ultimos_consumos_por_materia_prima(limit: int = 30) -> list[dict[str, Any]]:
    n = int(limit or 30)
    if n < 1:
        n = 1
    if n > 200:
        n = 200

    rank_col = func.row_number().over(
        partition_by=func.lower(func.trim(ConsumoStock.producto)),
        order_by=(ConsumoStock.created_at_iso.desc(), ConsumoStock.id.desc()),
    )
    ranked = select(ConsumoStock.id.label("cid"), rank_col.label("rn")).where(
        and_(ConsumoStock.categoria == "materia_prima")
    ).subquery()
    rows = db.session.scalars(
        select(ConsumoStock)
        .join(ranked, ranked.c.cid == ConsumoStock.id)
        .where(ranked.c.rn == 1)
        .order_by(ConsumoStock.producto.asc())
        .limit(n)
    ).all()

    equipo_ids = {int(r.equipo_id) for r in rows if r.equipo_id}
    equipos_by_id: dict[int, str] = {}
    if equipo_ids:
        eq_rows = db.session.scalars(select(Equipo).where(Equipo.id.in_(equipo_ids))).all()
        equipos_by_id = {int(e.id): str(e.nombre_equipo) for e in eq_rows}

    out: list[dict[str, Any]] = []
    for r in rows:
        eq_name = equipos_by_id.get(int(r.equipo_id), "") if r.equipo_id else ""
        out.append(
            {
                "producto": r.producto,
                "fecha_hora": format_consumo_stock_panel_datetime(r.created_at_iso, r.fecha, r.hora),
                "cantidad": r.cantidad,
                "unidad": "",
                "equipo": eq_name,
                "operador": r.operador,
                "observaciones": (r.observaciones or "").strip(),
            }
        )
    return out


def build_dashboard_template_context(user: "User | None") -> dict[str, Any]:
    """
    Datos agregados para ``dashboard.html`` según permisos del usuario (sin HTTP).
    """
    from app.auth_utils import user_can, user_can_access_stock_hub
    from app.services import stock_service

    alertas_stock: list[dict[str, Any]] = []
    ultimos_hipoclorito: list[dict[str, Any]] = []
    ultimo_salmuera: dict[str, Any] | None = None
    ultimo_agua: dict[str, Any] | None = None
    ultimos_consumos_mp: list[dict[str, Any]] = []

    u = user
    if u and user_can_access_stock_hub(u):
        try:
            alertas_stock = stock_service.alertas_bajo_stock(limit=30)
        except Exception:
            alertas_stock = []
    if u and (u.is_admin or user_can(u, "salmuera")):
        try:
            ultimos_hipoclorito = ultimos_hipoclorito_por_rectificador(limit=30)
        except Exception:
            ultimos_hipoclorito = []
    if u and (u.is_admin or user_can(u, "reactor")):
        try:
            ultimo_salmuera = ultimo_registro_salmuera()
        except Exception:
            ultimo_salmuera = None
    if u and (u.is_admin or user_can(u, "agua")):
        try:
            ultimo_agua = ultimo_registro_agua()
        except Exception:
            ultimo_agua = None
    if u and user_can_access_stock_hub(u):
        try:
            ultimos_consumos_mp = ultimos_consumos_por_materia_prima(limit=50)
        except Exception:
            ultimos_consumos_mp = []

    return {
        "alertas_stock": alertas_stock,
        "ultimos_hipoclorito": ultimos_hipoclorito,
        "ultimo_salmuera": ultimo_salmuera,
        "ultimo_agua": ultimo_agua,
        "ultimos_consumos_mp": ultimos_consumos_mp,
    }
