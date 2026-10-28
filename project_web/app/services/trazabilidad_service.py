"""Trazabilidad del hipoclorito: lote de despacho ⇄ producción ⇄ lotes de materia prima.

Los dos tanques de producto se usan como un pulmón: lo que sale en un camión es una mezcla
de lo producido antes. El *origen* de una carga es la ventana de producción hacia atrás desde
la carga que repone ``FACTOR_PULMON`` veces el stock que había en tanques (último cierre de
turno). En un tanque bien mezclado, con 3 volúmenes renovados queda menos del 5 % de producto
más viejo (e⁻³), así que la ventana cubre ~95 % de lo que lleva el camión.

Por turno (entre dos cierres recepcionados) se toma como entrada a los tanques:
producción = stock_cierre − stock_cierre_anterior + camiones cargados − ingresos PT (si da
negativa por error de medición, cuenta 0) más los ingresos de hipoclorito comprado.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.constants import ENTREGAS_STOCK_CATEGORIA
from app.extensions import db
from app.models import (
    AguaRegistro,
    ConsumoStock,
    Entrega,
    IngresoStock,
    ReactorRegistro,
    SalmueraRegistro,
    ShiftHandover,
    ShiftSession,
    User,
)
from app.services import lote_produccion_service as lp
from app.services import shift_handover_service as sh
from app.utils.hipoclorito_producto import entrega_columna_es_hipoclorito_operativo_sql

FACTOR_PULMON = 3.0
VENTANA_MAXIMA = timedelta(days=15)


def _iso(fecha: str | None, hora: str | None = None) -> str:
    """Fecha+hora a ISO local comparable como texto (YYYY-MM-DDTHH:MM[:SS])."""
    f = (fecha or "").strip()
    h = (hora or "").strip()
    return f"{f}T{h}" if h else f


def _menos(iso: str, delta: timedelta) -> str:
    return (datetime.fromisoformat(iso[:19]) - delta).isoformat(timespec="seconds")


@dataclass
class _Turno:
    desde: str
    hasta: str
    stock: float
    entrada: float
    handover_id: int
    operador_user_id: int
    lote: str | None
    observado: str | None


class _Pulmon:
    """Cierres de turno, cargas e ingresos de hipoclorito en memoria (una consulta de cada uno)."""

    def __init__(self) -> None:
        hos = db.session.scalars(
            select(ShiftHandover)
            .where(ShiftHandover.status == sh.HANDOVER_RECEIVED)
            .order_by(ShiftHandover.handed_over_at_iso, ShiftHandover.id)
        ).all()
        cierres = [h for h in hos if (h.handed_over_at_iso or "").strip() and h.hypochlorite_stock_liters is not None]
        sesiones = {
            int(sid): (lote, nota)
            for sid, lote, nota in db.session.execute(
                select(ShiftSession.id, ShiftSession.lote_produccion, ShiftSession.lote_observado_nota)
            )
        }
        hipo_e = entrega_columna_es_hipoclorito_operativo_sql(Entrega.producto)
        cargas = db.session.execute(
            select(Entrega.cargada_at_iso, func.coalesce(Entrega.cantidad_real_cargada, Entrega.cantidad_programada, Entrega.cantidad))
            .where(Entrega.carga_origen_entrega_id.is_(None), Entrega.cargada_at_iso.isnot(None), hipo_e)
            .order_by(Entrega.cargada_at_iso)
        ).all()
        hipo_i = entrega_columna_es_hipoclorito_operativo_sql(IngresoStock.producto)
        ingresos = db.session.execute(
            select(IngresoStock.created_at_iso, IngresoStock.cantidad)
            .where(IngresoStock.categoria == ENTREGAS_STOCK_CATEGORIA, hipo_i)
            .order_by(IngresoStock.created_at_iso)
        ).all()
        self._cargas_t = [str(t) for t, _ in cargas]
        self._cargas_acum = _acumulado(float(q or 0) for _, q in cargas)
        self._ingr_t = [str(t) for t, _ in ingresos]
        self._ingr_acum = _acumulado(float(q or 0) for _, q in ingresos)
        self.turnos: list[_Turno] = []
        for prev, h in zip(cierres, cierres[1:]):
            t0, t1 = prev.handed_over_at_iso, h.handed_over_at_iso
            cargado = self._suma(self._cargas_t, self._cargas_acum, t0, t1)
            ingresado = self._suma(self._ingr_t, self._ingr_acum, t0, t1)
            produccion = float(h.hypochlorite_stock_liters) - float(prev.hypochlorite_stock_liters) + cargado - ingresado
            lote, observado = sesiones.get(int(h.shift_session_id), (None, None))
            self.turnos.append(
                _Turno(
                    t0, t1, float(h.hypochlorite_stock_liters), max(0.0, produccion) + ingresado,
                    int(h.id), int(h.outgoing_user_id), lote, observado,
                )
            )
        self._fin = [t.hasta for t in self.turnos]

    @staticmethod
    def _suma(ts: list[str], acum: list[float], desde: str, hasta: str) -> float:
        """Suma de (desde, hasta]."""
        return acum[bisect.bisect_right(ts, hasta)] - acum[bisect.bisect_right(ts, desde)]

    def ventana(self, hasta: str) -> dict[str, Any]:
        """Ventana de producción que llenó el pulmón hasta ``hasta`` (momento de la carga)."""
        limite = _menos(hasta, VENTANA_MAXIMA)
        j = bisect.bisect_right(self._fin, hasta) - 1
        if j < 0:
            return {"desde": limite, "hasta": hasta, "stock": None, "cubierto": 0.0, "completa": False, "turnos": []}
        stock = self.turnos[j].stock
        objetivo = FACTOR_PULMON * stock
        cubierto = 0.0
        i = j
        while i >= 0 and cubierto < objetivo and self.turnos[i].desde >= limite:
            cubierto += self.turnos[i].entrada
            i -= 1
        usados = self.turnos[i + 1 : j + 1]
        desde = usados[0].desde if usados else self.turnos[j].hasta
        return {
            "desde": desde,
            "hasta": hasta,
            "stock": stock,
            "cubierto": cubierto,
            "completa": cubierto >= objetivo,
            "turnos": usados,
        }


def _acumulado(valores) -> list[float]:
    out = [0.0]
    for v in valores:
        out.append(out[-1] + v)
    return out


def _nombres_usuarios(ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    from app.auth_utils import user_display_name

    return {int(u.id): user_display_name(u) for u in db.session.scalars(select(User).where(User.id.in_(ids)))}


def _iso_consumo():
    return ConsumoStock.fecha + "T" + ConsumoStock.hora


def _materias_primas(desde: str, hasta: str) -> list[dict[str, Any]]:
    """Lotes de MP consumidos en la ventana, más el lote que estaba en uso al empezar (por producto)."""
    t = _iso_consumo()
    filas = db.session.execute(
        select(ConsumoStock.producto, ConsumoStock.ingreso_stock_id, func.sum(ConsumoStock.cantidad), func.min(t), func.max(t))
        .where(ConsumoStock.categoria == "materia_prima", t >= desde, t <= hasta)
        .group_by(ConsumoStock.producto, ConsumoStock.ingreso_stock_id)
    ).all()
    lineas = [
        {"producto": p, "ingreso_id": iid, "cantidad": float(c or 0), "primero": a, "ultimo": b, "previo": False}
        for p, iid, c, a, b in filas
    ]
    productos = {p for p, *_ in filas} | set(
        db.session.scalars(select(ConsumoStock.producto).where(ConsumoStock.categoria == "materia_prima").distinct())
    )
    en_ventana = {(x["producto"], x["ingreso_id"]) for x in lineas}
    for p in productos:
        prev = db.session.execute(
            select(ConsumoStock.ingreso_stock_id, t)
            .where(ConsumoStock.categoria == "materia_prima", ConsumoStock.producto == p, ConsumoStock.ingreso_stock_id.isnot(None), t < desde)
            .order_by(t.desc())
            .limit(1)
        ).first()
        if prev and (p, prev[0]) not in en_ventana and prev[1] >= _menos(desde, VENTANA_MAXIMA):
            lineas.append({"producto": p, "ingreso_id": prev[0], "cantidad": 0.0, "primero": prev[1], "ultimo": prev[1], "previo": True})
    ids = {x["ingreso_id"] for x in lineas if x["ingreso_id"]}
    ingresos = {int(i.id): i for i in db.session.scalars(select(IngresoStock).where(IngresoStock.id.in_(ids)))} if ids else {}
    for x in lineas:
        ing = ingresos.get(x["ingreso_id"] or 0)
        x["lote"] = (ing.lote or "").strip() if ing else ""
        x["proveedor"] = ((ing.proveedor or ing.marca or "").strip()) if ing else ""
        x["vencimiento"] = (ing.vencimiento or "").strip() if ing else ""
        x["unidad"] = (ing.unidad or "").strip() if ing else ""
    return sorted(lineas, key=lambda x: (x["producto"].lower(), x["primero"]))


def _hipo_comprado(desde: str, hasta: str) -> list[IngresoStock]:
    hipo = entrega_columna_es_hipoclorito_operativo_sql(IngresoStock.producto)
    return list(
        db.session.scalars(
            select(IngresoStock)
            .where(IngresoStock.categoria == ENTREGAS_STOCK_CATEGORIA, hipo, IngresoStock.created_at_iso > desde, IngresoStock.created_at_iso <= hasta)
            .order_by(IngresoStock.created_at_iso)
        )
    )


def _analisis(desde: str, hasta: str) -> dict[str, Any]:
    def en_ventana(modelo):
        t = modelo.fecha_iso + "T" + modelo.hora_hm
        return t >= desde, t <= hasta

    salmuera = list(db.session.scalars(select(SalmueraRegistro).where(*en_ventana(SalmueraRegistro))))
    conc = [float(r.hipo_conc) for r in salmuera if r.hipo_conc]
    t_s = SalmueraRegistro.fecha_iso + "T" + SalmueraRegistro.hora_hm
    ultimo = db.session.scalars(
        select(SalmueraRegistro).where(t_s <= hasta).order_by(t_s.desc(), SalmueraRegistro.id.desc()).limit(1)
    ).first()
    return {
        "salmuera": len(salmuera),
        "reactor": db.session.scalar(select(func.count()).select_from(ReactorRegistro).where(*en_ventana(ReactorRegistro))) or 0,
        "agua": db.session.scalar(select(func.count()).select_from(AguaRegistro).where(*en_ventana(AguaRegistro))) or 0,
        "conc_min": min(conc) if conc else None,
        "conc_max": max(conc) if conc else None,
        "conc_prom": sum(conc) / len(conc) if conc else None,
        "ultimo": ultimo,
    }


def detalle_lote_despacho(lote: str) -> dict[str, Any] | None:
    """Hacia atrás: de un lote de despacho a turnos, análisis y lotes de MP."""
    lote = (lote or "").strip().upper()
    entregas = list(db.session.scalars(select(Entrega).where(Entrega.lote_despacho == lote).order_by(Entrega.id)))
    if not entregas:
        return None
    origen = next((e for e in entregas if e.carga_origen_entrega_id is None), entregas[0])
    hasta = (origen.cargada_at_iso or "").strip()
    v = _Pulmon().ventana(hasta)
    nombres = _nombres_usuarios({t.operador_user_id for t in v["turnos"]})
    en_curso = lp.turno_en(hasta)
    observados = {t.lote: t.observado for t in v["turnos"] if t.observado}
    if en_curso is not None and en_curso.lote_observado_nota:
        observados[en_curso.lote_produccion] = en_curso.lote_observado_nota
    return {
        "lote": lote,
        "lote_en_curso": en_curso,
        "observados": observados,
        "entregas": entregas,
        "origen": origen,
        "ventana": v,
        "turnos": [{"t": t, "operador": nombres.get(t.operador_user_id, "")} for t in v["turnos"]],
        "analisis": _analisis(v["desde"], hasta),
        "materias_primas": _materias_primas(v["desde"], hasta),
        "hipo_comprado": _hipo_comprado(v["desde"], hasta),
    }


def _cargas_afectadas(desde: str, hasta: str) -> list[dict[str, Any]]:
    """Cargas cuyo origen se superpone con [desde, hasta]."""
    hipo = entrega_columna_es_hipoclorito_operativo_sql(Entrega.producto)
    tope = (datetime.fromisoformat(hasta[:19]) + VENTANA_MAXIMA).isoformat(timespec="seconds")
    candidatas = list(
        db.session.scalars(
            select(Entrega)
            .where(
                Entrega.carga_origen_entrega_id.is_(None),
                Entrega.cargada_at_iso >= desde,
                Entrega.cargada_at_iso <= tope,
                hipo,
            )
            .order_by(Entrega.cargada_at_iso)
        )
    )
    if not candidatas:
        return []
    pulmon = _Pulmon()
    out = []
    for e in candidatas:
        v = pulmon.ventana(e.cargada_at_iso)
        if v["desde"] <= hasta:
            hermanas = list(db.session.scalars(select(Entrega).where(Entrega.lote_despacho == e.lote_despacho))) if e.lote_despacho else [e]
            out.append({"carga": e, "entregas": hermanas, "ventana": v})
    return out


def rastrear_ingreso(ingreso_id: int) -> dict[str, Any] | None:
    """Hacia adelante: de un lote de ingreso (MP o hipoclorito comprado) a las cargas y clientes."""
    ing = db.session.get(IngresoStock, int(ingreso_id))
    if ing is None:
        return None
    if ing.categoria == ENTREGAS_STOCK_CATEGORIA:
        desde = hasta = (ing.created_at_iso or "").strip()
        uso = {"desde": desde, "hasta": None, "consumos": 0}
    else:
        t = _iso_consumo()
        a, b, n = db.session.execute(
            select(func.min(t), func.max(t), func.count()).where(ConsumoStock.ingreso_stock_id == ing.id)
        ).one()
        if not n:
            return {"ingreso": ing, "uso": None, "cargas": []}
        # El lote sigue en el proceso hasta que se empieza a usar otro lote del mismo producto.
        reemplazo = db.session.scalar(
            select(func.min(t)).where(
                ConsumoStock.producto == ing.producto,
                ConsumoStock.categoria == ing.categoria,
                ConsumoStock.ingreso_stock_id.isnot(None),
                ConsumoStock.ingreso_stock_id != ing.id,
                t > b,
            )
        )
        desde, hasta = a, (reemplazo or sh.now_local_iso())
        uso = {"desde": a, "hasta": reemplazo, "consumos": n}
    return {"ingreso": ing, "uso": uso, "cargas": _cargas_afectadas(desde, hasta)}


def buscar(q: str) -> dict[str, Any]:
    """Un lote de despacho (D…) o un lote de ingreso de MP / hipoclorito comprado."""
    q = (q or "").strip()
    if not q:
        return {"tipo": None}
    if db.session.scalar(select(Entrega.id).where(Entrega.lote_despacho == q.upper()).limit(1)):
        return {"tipo": "despacho", "lote": q.upper()}
    if lp.turno_de_lote(q) is not None:
        return {"tipo": "produccion", "lote": q.upper()}
    ingresos = list(
        db.session.scalars(
            select(IngresoStock)
            .where(func.lower(func.trim(IngresoStock.lote)) == q.lower(), IngresoStock.categoria != "laboratorio")
            .order_by(IngresoStock.created_at_iso.desc())
        )
    )
    return {"tipo": "ingresos", "ingresos": ingresos}


def detalle_lote_produccion(lote: str) -> dict[str, Any] | None:
    """Un turno: quién, cuándo, análisis, lotes de MP y camiones que pueden llevar su producto."""
    turno = lp.turno_de_lote(lote)
    if turno is None:
        return None
    desde = turno.started_at_iso
    siguiente = lp.inicio_turno_siguiente(turno)
    hasta = siguiente or sh.now_local_iso()
    ids = {int(turno.user_id)} | ({int(turno.laboratorist_user_id)} if turno.laboratorist_user_id else set())
    if turno.lote_observado_por_user_id:
        ids.add(int(turno.lote_observado_por_user_id))
    nombres = _nombres_usuarios(ids)
    cierre = db.session.scalars(select(ShiftHandover).where(ShiftHandover.shift_session_id == turno.id)).first()
    salmuera = list(
        db.session.scalars(
            select(SalmueraRegistro).where(SalmueraRegistro.lote == turno.lote_produccion).order_by(SalmueraRegistro.fecha_iso, SalmueraRegistro.hora_hm)
        )
    )
    conc = [float(r.hipo_conc) for r in salmuera if r.hipo_conc]
    return {
        "lote": turno.lote_produccion,
        "turno": turno,
        "desde": desde,
        "hasta": hasta,
        "en_curso": siguiente is None,
        "operador": nombres.get(int(turno.user_id), ""),
        "laboratorista": nombres.get(int(turno.laboratorist_user_id), "") if turno.laboratorist_user_id else "",
        "observado_por": nombres.get(int(turno.lote_observado_por_user_id), "") if turno.lote_observado_por_user_id else "",
        "cierre": cierre,
        "salmuera": salmuera,
        "conc_min": min(conc) if conc else None,
        "conc_max": max(conc) if conc else None,
        "conc_prom": sum(conc) / len(conc) if conc else None,
        "reactor": db.session.scalar(select(func.count()).select_from(ReactorRegistro).where(ReactorRegistro.lote == turno.lote_produccion)) or 0,
        "agua": db.session.scalar(select(func.count()).select_from(AguaRegistro).where(AguaRegistro.lote == turno.lote_produccion)) or 0,
        "materias_primas": [m for m in _materias_primas(desde, hasta) if not m["previo"]],
        "cargas": _cargas_afectadas(desde, hasta),
    }
