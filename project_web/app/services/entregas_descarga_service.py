"""
Descarga del camión por el chofer: en cada punto informa destino y litros descargados.

Una carga (fila origen) puede descargarse en uno o varios puntos:
- si logística ya asignó ese destino en el grupo de la carga, se marca esa entrega como entregada;
- si la carga todavía no tiene destino, la primera descarga se lo asigna a la fila origen;
- si es un punto nuevo, se crea una entrega hermana del mismo grupo (sin nuevo consumo de stock).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import ClienteEntrega, Entrega, LugarEntrega, User
from app.services import entregas_service as es

# Tolerancia de medición: se puede informar hasta un 5 % más de lo que queda en el camión.
TOLERANCIA_DESCARGA = 0.05


def litros_descargados(origen: Entrega) -> float:
    grupo = [origen, *es.listar_hermanas_carga(origen)]
    return sum(float(e.cantidad_real_entregada or 0) for e in grupo if (e.estado or "") == "entregada")


def litros_restantes(entrega: Entrega) -> float:
    """Litros que quedan en el camión de esa carga (0 si todavía no se cargó).

    Si llevó agua, se cuenta en el camión: el chofer informa lo que descarga (mezcla incluida)."""
    origen = es.origen_carga_de(entrega)
    if origen.cantidad_real_cargada is None:
        return 0.0
    total = float(origen.cantidad_real_cargada) + float(origen.agua_litros or 0)
    return max(0.0, total - litros_descargados(origen))


def destinos_activos() -> list[tuple[LugarEntrega, ClienteEntrega]]:
    rows = db.session.execute(
        select(LugarEntrega, ClienteEntrega)
        .join(ClienteEntrega, ClienteEntrega.id == LugarEntrega.cliente_id)
        .where(LugarEntrega.activo.is_(True), ClienteEntrega.activo.is_(True))
        .order_by(ClienteEntrega.nombre, LugarEntrega.nombre)
    ).all()
    return [(lug, cli) for lug, cli in rows]


def _palabras(s: str) -> set[str]:
    s = "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")
    return {w for w in re.split(r"[^a-z0-9]+", s) if w}


def nombre_destino(lug: LugarEntrega, cli: ClienteEntrega) -> str:
    return f"{cli.nombre} · {lug.nombre}"


def buscar_destino(texto: str) -> tuple[LugarEntrega, ClienteEntrega]:
    """Destino del catálogo por texto libre («Buena Esperanza», «EPAS Chos Malal»). Ambiguo o inexistente → ValueError."""
    buscado = _palabras(texto)
    if not buscado:
        raise ValueError("Indicá el destino de la descarga.")
    todos = destinos_activos()
    hits = [(l, c) for l, c in todos if buscado <= _palabras(f"{c.nombre} {l.nombre}")]
    # Mismo cliente y lugar repetidos en el catálogo: cuenta como uno.
    unicos = {nombre_destino(l, c).lower(): (l, c) for l, c in hits}
    if len(unicos) == 1:
        return next(iter(unicos.values()))
    if len(unicos) > 1:
        opciones = ", ".join(sorted(unicos))
        raise ValueError(f"Hay varios destinos con «{texto}»: {opciones}. ¿Cuál?")
    parecidos = sorted({nombre_destino(l, c) for l, c in todos if buscado & _palabras(f"{c.nombre} {l.nombre}")})
    extra = f" Parecidos: {', '.join(parecidos[:8])}." if parecidos else ""
    raise ValueError(f"No encontré «{texto}» en los destinos del sistema; logística tiene que darlo de alta.{extra}")


def destino_por_id(lugar_id: int) -> tuple[LugarEntrega, ClienteEntrega]:
    lug = db.session.get(LugarEntrega, int(lugar_id))
    cli = db.session.get(ClienteEntrega, int(lug.cliente_id)) if lug is not None else None
    if lug is None or cli is None or not lug.activo or not cli.activo:
        raise ValueError("Destino inválido o inactivo.")
    return lug, cli


def carga_abierta_del_chofer(chofer_nombre: str, ahora: datetime) -> Entrega:
    """Última carga del chofer (últimos 7 días) que todavía tiene litros en el camión."""
    desde = (ahora - timedelta(days=7)).isoformat(timespec="seconds")
    origenes = db.session.scalars(
        select(Entrega)
        .where(
            es.sql_es_origen_carga(),
            Entrega.chofer_previsto == chofer_nombre,
            Entrega.cantidad_real_cargada.is_not(None),
            Entrega.cargada_at_iso >= desde,
        )
        .order_by(Entrega.cargada_at_iso.desc(), Entrega.id.desc())
    ).all()
    for o in origenes:
        if litros_restantes(o) > 0:
            return o
    raise ValueError(f"{chofer_nombre} no tiene una carga con litros en el camión. Primero registrá la carga.")


def validar_descarga(origen: Entrega, litros: float) -> float:
    """Devuelve lo que queda en el camión antes de descargar; error si se pasa."""
    origen = es.origen_carga_de(origen)
    if origen.cantidad_real_cargada is None:
        raise ValueError("Esa entrega todavía no se cargó en el camión.")
    if litros <= 0 or litros != litros:
        raise ValueError("Los litros descargados tienen que ser más que cero.")
    restante = litros_restantes(origen)
    if restante <= 0:
        raise ValueError(f"La carga #{origen.id} ya se descargó completa.")
    if litros > restante * (1 + TOLERANCIA_DESCARGA):
        raise ValueError(f"En el camión quedan {restante:g} L de la carga #{origen.id}; no se pueden descargar {litros:g} L.")
    return restante


def registrar_descarga(
    entrega: Entrega, lug: LugarEntrega, cli: ClienteEntrega, litros: float, actor: User | None, ahora: datetime
) -> tuple[Entrega, float]:
    """Registra la descarga en ese destino. Devuelve (entrega marcada como entregada, litros que quedan en el camión)."""
    origen = es.origen_carga_de(entrega)
    restante = validar_descarga(origen, litros)
    iso = ahora.isoformat(timespec="seconds")
    grupo = [origen, *es.listar_hermanas_carga(origen)]
    destino = next(
        (
            e
            for e in grupo
            if (e.estado or "") == "cargada" and not es.entrega_pendiente_logistica(e) and e.lugar_entrega_id == lug.id
        ),
        None,
    )
    if destino is None and es.entrega_pendiente_logistica(origen):
        destino = origen
        origen.cliente_id, origen.cliente = int(cli.id), str(cli.nombre).strip()
        origen.lugar_entrega_id, origen.lugar_entrega = int(lug.id), str(lug.nombre).strip()
        origen.cantidad = origen.cantidad_programada = litros
        origen.updated_at_iso = iso
    if destino is None:
        destino = Entrega(
            cliente=str(cli.nombre).strip(),
            lugar_entrega=str(lug.nombre).strip(),
            producto=str(origen.producto or "").strip(),
            cliente_id=int(cli.id),
            lugar_entrega_id=int(lug.id),
            producto_terminado_id=origen.producto_terminado_id,
            chofer_entrega_id=origen.chofer_entrega_id,
            chofer_previsto=origen.chofer_previsto,
            cantidad=litros,
            cantidad_programada=litros,
            unidad=origen.unidad,
            fecha_prevista=ahora.date().isoformat(),
            estado="cargada",
            created_at_iso=iso,
            updated_at_iso=iso,
            created_by_user_id=int(actor.id) if actor else None,
            cargada_at_iso=origen.cargada_at_iso,
            cargada_by_user_id=origen.cargada_by_user_id,
            stock_categoria=origen.stock_categoria,
            stock_marca=origen.stock_marca,
            stock_equipo_id=origen.stock_equipo_id,
            carga_grupo_id=es.ensure_carga_grupo(origen),
            carga_origen_entrega_id=int(origen.id),
        )
        db.session.add(destino)
        db.session.flush()
        es.append_evento(
            int(destino.id), "creada", iso, actor, es._actor_display(actor),
            {"origen": "descarga_chofer", "carga_origen_entrega_id": int(origen.id), "cantidad_descargar": litros},
        )
    es.ensure_carga_grupo(origen)
    es.ejecutar_entregada(destino, actor, ahora, litros)
    return destino, max(0.0, restante - litros)
