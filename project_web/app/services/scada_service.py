"""
Vista de planta tipo SCADA: foto del estado actual armada con lo que se carga en el sistema
(registros de electrolizadores, circuito de salmuera, agua, filtro, stock, turno, paradas y cronómetros).

Cada bloque se arma por separado: si uno falla, el resto de la vista sigue mostrando datos.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from sqlalchemy import func, select

from app.constants import SALMUERA_PANEL_ELECTROLIZADORES
from app.extensions import db
from app.models import (
    AguaRegistro,
    BolsonRegistro,
    ColumnaIntercambio,
    Entrega,
    FiltroLavadoRegistro,
    ProductoCatalogo,
    ReactorRegistro,
    SalmueraRegistro,
)
from app.services import operational_warnings as ow
from app.services import plant_stop_service as ps
from app.services import salmuera_analisis_8hs_service as a8_svc
from app.services import shift_handover_service as sh
from app.services import stock_service
from app.services import timer_overdue_service
from app.utils.fechas import fecha_ar

log = logging.getLogger(__name__)

# Materias primas que se muestran como silos/tanques, en el orden del proceso.
MATERIAS_PRIMAS = (
    ("Sal Gruesa Lavada", "Sal", "bolsones"),
    ("Carbonato de Sodio", "Carbonato", "bolsas"),
    ("Soda Caustica 50%", "Soda 50 %", "L"),
    ("Acido Clorhidrico 30%", "Ácido 30 %", "L"),
    ("Sulfito de Sodio", "Sulfito", "bolsas"),
    ("Filtros de Papel 1 micron", "Filtros 1 µm", "u."),
)


def _ts(fecha_iso: str | None, hora_hm: str | None) -> str:
    f = fecha_ar((fecha_iso or "").strip()) if fecha_iso else ""
    return f"{f} {(hora_hm or '').strip()}".strip()


def _ultimo(model: Any, *where: Any) -> Any:
    return db.session.scalars(
        select(model).where(*where).order_by(model.created_at_iso.desc(), model.id.desc()).limit(1)
    ).first()


def _bloque(nombre: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception:
        log.exception("SCADA: no se pudo armar el bloque %s", nombre)
        db.session.rollback()
        return {"error": True}


def _parada(circuito: str) -> dict[str, Any] | None:
    ev = ps.get_active_stop(circuito)
    return ps.event_to_dict(ev) if ev is not None else None


def _electrolizadores() -> list[dict[str, Any]]:
    out = []
    for eid in SALMUERA_PANEL_ELECTROLIZADORES:
        r = _ultimo(SalmueraRegistro, SalmueraRegistro.electrolizador == int(eid))
        item: dict[str, Any] = {
            "id": int(eid),
            "nombre": f"Electrolizador {eid}",
            "parada": _parada(ps.circuit_key_for_electrolizador(int(eid))),
            "registro": None,
        }
        if r is not None:
            try:
                voltajes = [float(v) for v in json.loads(r.voltajes_json or "[]")]
            except (TypeError, ValueError):
                voltajes = []
            item["registro"] = {
                "cuando": _ts(r.fecha_iso, r.hora_hm),
                "operador": r.operador,
                "lote": (r.lote or "").strip(),
                "celdas": r.cantidad_celdas,
                "voltajes": voltajes,
                "voltaje_total": r.voltaje_total,
                "voltaje_trafo": r.voltaje_total_trafo,
                "amperaje": r.amperaje,
                "caudal_agua": r.caudal_agua_l_h,
                "caudal_salmuera": r.caudal_salmuera_l_h,
                "hipo_conc": r.hipo_conc,
                "hipo_exceso_soda": r.hipo_exceso_soda,
                "sal_temp": r.sal_temp,
                "sal_conc": r.sal_conc,
                "sal_ph": r.sal_ph,
                "soda_conc": r.soda_conc,
                "declor_ph": r.declor_ph,
                "orp": r.orp,
                "observaciones": (r.observaciones or "").strip(),
                "avisos": ow.warnings_for_salmuera_registro(r),
            }
        out.append(item)
    return out


def _circuito_salmuera() -> dict[str, Any]:
    r = _ultimo(ReactorRegistro)
    a8 = a8_svc.latest_row()
    f = _ultimo(FiltroLavadoRegistro)
    b = _ultimo(BolsonRegistro)
    return {
        "parada": _parada(ps.CIRCUIT_REACTOR),
        "parada_filtro": _parada(ps.CIRCUIT_FILTRO),
        "reactor": None
        if r is None
        else {
            "cuando": _ts(r.fecha_iso, r.hora_hm),
            "operador": r.operador,
            "lote": r.lote,
            "ph": r.ph,
            "temperatura": r.temperatura,
            "densidad": r.densidad,
            "concentracion": r.concentracion_tabla,
            "exceso_naoh": r.exceso_naoh,
            "exceso_na2co3": r.exceso_na2co3,
            "orp": r.orp,
            "e2": {"temperatura": r.e2_temperatura, "densidad": r.e2_densidad, "concentracion": r.e2_concentracion},
            "e3": {"temperatura": r.e3_temperatura, "densidad": r.e3_densidad, "concentracion": r.e3_concentracion},
            "observaciones": (r.observaciones or "").strip(),
            "avisos": ow.warnings_for_reactor_registro(r),
        },
        "analisis_8hs": None
        if a8 is None
        else {
            "cuando": _ts(a8.fecha, a8.hora),
            "operador": a8.operador,
            "dureza": a8.dureza_salmuera,
            "cloro_libre": a8.cloro_libre_salmuera,
        },
        "filtro": None if f is None else {"cuando": _ts(f.fecha_iso, f.hora_hm), "operador": f.operador},
        "bolson": None if b is None else {"cuando": _ts(b.fecha_iso, b.hora_hm)},
    }


def _agua() -> dict[str, Any]:
    r = _ultimo(AguaRegistro)
    rank = func.row_number().over(
        partition_by=ColumnaIntercambio.columna_numero,
        order_by=(ColumnaIntercambio.updated_at_iso.desc(), ColumnaIntercambio.id.desc()),
    )
    sub = select(ColumnaIntercambio.id.label("cid"), rank.label("rn")).subquery()
    columnas = db.session.scalars(
        select(ColumnaIntercambio)
        .join(sub, sub.c.cid == ColumnaIntercambio.id)
        .where(sub.c.rn == 1)
        .order_by(ColumnaIntercambio.columna_numero)
    ).all()
    return {
        "parada": _parada(ps.CIRCUIT_AGUA),
        "registro": None
        if r is None
        else {
            "cuando": _ts(r.fecha_iso, r.hora_hm),
            "operador": r.operador,
            "columna": r.numero_columna,
            "temperatura": r.temperatura,
            "dureza": r.dureza,
            "avisos": ow.warnings_for_agua_registro(r),
        },
        "columnas": [
            {
                "numero": c.columna_numero,
                "estado": c.estado,
                "dureza_salida": c.dureza_salida_ppm,
                "regeneracion": _ts(c.fecha_regeneracion, c.hora_regeneracion),
            }
            for c in columnas
        ],
    }


def _materias_primas() -> list[dict[str, Any]]:
    stock = {r["producto"]: float(r["stock"]) for r in stock_service.stock_consolidado("materia_prima")}
    minimos = {
        c.nombre_producto: c.stock_minimo_alerta
        for c in db.session.scalars(select(ProductoCatalogo).where(ProductoCatalogo.categoria == "materia_prima"))
    }
    out = []
    for nombre, etiqueta, unidad in MATERIAS_PRIMAS:
        actual = stock.get(nombre, 0.0)
        minimo = minimos.get(nombre)
        nivel = "ok"
        if minimo:
            nivel = "critico" if actual < minimo else ("limite" if actual <= minimo * 1.5 else "ok")
        out.append(
            {"producto": nombre, "etiqueta": etiqueta, "unidad": unidad, "stock": actual, "minimo": minimo, "nivel": nivel}
        )
    return out


def _hipoclorito() -> dict[str, Any]:
    from app.services.shift_hypochlorite_indicators_service import get_carga_available, get_instant_stock

    hoy = ps.today_operacion_iso()
    programadas = db.session.scalars(
        select(Entrega).where(Entrega.estado == "programada", Entrega.fecha_prevista <= hoy).order_by(Entrega.fecha_prevista)
    ).all()
    cargadas_hoy = db.session.scalars(
        select(Entrega).where(Entrega.cargada_at_iso >= hoy, Entrega.estado != "programada")
    ).all()
    hipo = [e for e in programadas if stock_service.producto_entrega_es_stock_hipoclorito(e.producto)]
    return {
        "stock": get_instant_stock(),
        "para_carga": get_carga_available(),
        "programadas": [
            {
                "cliente": e.cliente,
                "litros": e.cantidad_programada or e.cantidad,
                "fecha": fecha_ar(e.fecha_prevista),
            }
            for e in hipo[:6]
        ],
        "programadas_litros": sum(float(e.cantidad_programada or e.cantidad or 0) for e in hipo),
        "cargadas_hoy": len(cargadas_hoy),
        "cargadas_hoy_litros": sum(float(e.cantidad_real_cargada or e.cantidad or 0) for e in cargadas_hoy),
    }


def _turno() -> dict[str, Any]:
    s = sh.get_open_shift_session()
    pend = sh.get_pending_handover()
    return {
        "abierto": s is not None,
        "operador": sh.format_shift_operator_display(s) if s else "",
        "desde": (s.started_at_iso or "").replace("T", " ")[:16] if s else "",
        "pendiente_recepcion": pend is not None,
    }


def snapshot() -> dict[str, Any]:
    return {
        "generado": _bloque("hora", lambda: fecha_ar(ps.now_local_iso()[:16].replace("T", " "))),
        "turno": _bloque("turno", _turno),
        "cronometros": _bloque("cronometros", lambda: timer_overdue_service.list_timer_statuses()["timers"]),
        "electrolizadores": _bloque("electrolizadores", _electrolizadores),
        "salmuera": _bloque("salmuera", _circuito_salmuera),
        "agua": _bloque("agua", _agua),
        "materias_primas": _bloque("materias_primas", _materias_primas),
        "hipoclorito": _bloque("hipoclorito", _hipoclorito),
    }
