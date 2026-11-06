"""Diseño y desarrollo de producción (QDV-PO-03).

Un desarrollo (producto, materia prima, parámetro o etapa del proceso) tiene tres hojas que se imprimen como
los formularios del PO-03: 03_01 Planificación y control, 03_02 Entradas y salidas y 03_03 Revisión,
verificación, validación y aprobación. Los cambios de un desarrollo van en 03_04.

Lo que el sistema ya sabe sale solo del período de pruebas: resultados de laboratorio y de proceso (registros de
salmuera, reactor, agua y análisis de 8 hs), materias primas ingresadas y consumidas, operadores, lotes de
producción y procedimientos vigentes. A mano se completa solo lo que no está en el sistema. Las firmas son en el
sistema, como en las minutas; si el desarrollo se modifica después de firmado, las firmas se anulan.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    AguaRegistro,
    ConsumoStock,
    DesarrolloCambio,
    DesarrolloHistorial,
    DesarrolloProduccion,
    IngresoStock,
    ReactorRegistro,
    SalmueraAnalisis8hs,
    SalmueraRegistro,
    User,
)
from app.models.shift import ShiftSession
from app.services.fichas_proceso_service import fecha_local
from app.services.plan_accion_service import fecha_dmy, parse_fecha

REVISION = "00"
REGISTROS = {
    "01": "REGISTRO DE PLANIFICACIÓN Y CONTROL DEL DISEÑO Y DESARROLLO",
    "02": "REGISTRO DE ENTRADAS Y SALIDAS DE DISEÑO Y DESARROLLO",
    "03": "REGISTRO DE REVISIÓN, VERIFICACIÓN, VALIDACIÓN Y APROBACIÓN DEL DISEÑO Y DESARROLLO",
    "04": "REGISTRO DE CAMBIOS DE DISEÑO Y DESARROLLO",
}
TIPOS = ("Nuevo desarrollo", "Modificación")
ETAPAS = ("Identificación de requisitos", "Definición de entradas", "Desarrollo / modificación", "Revisión",
          "Verificación", "Validación, si corresponde", "Aprobación y liberación")
ESTADOS_ETAPA = ("Pendiente", "En curso", "Realizada", "No aplica")
SI_NO = ("Sí", "No")
RESULTADOS_APROBACION = ("APROBADO", "APROBADO CON OBSERVACIONES", "NO APROBADO")
RESULTADOS_CAMBIO = ("Sí", "No", "Sí, con observaciones")
METODOS_VERIFICACION = ("Ensayo de laboratorio", "Prueba de producción", "Comparación con especificaciones",
                        "Revisión documental")
OTROS_REQUISITOS = ("Cliente", "Legales / reglamentarios", "Internos", "Desarrollos anteriores", "Otros")
RECURSOS = ("personal", "equipos", "materias_primas", "ensayos", "documentacion")
RECURSOS_LABELS = {"personal": "Personal", "equipos": "Equipos / instalaciones", "materias_primas": "Materias primas / insumos",
                   "ensayos": "Ensayos / controles", "documentacion": "Documentación necesaria"}
# Requisitos del producto: especificación vigente del hipoclorito (PO-03 5.3) y de dónde sale el resultado.
PRODUCTO = (
    {"requisito": "Cloro activo", "especificacion": "Mínimo 100 g/L", "min": 100.0, "max": None, "campo": "hipo_conc", "unidad": "g/L"},
    {"requisito": "NaOH libre", "especificacion": "1,25 a 8,00 g/L", "min": 1.25, "max": 8.0, "campo": "hipo_exceso_soda", "unidad": "g/L"},
    {"requisito": "Densidad", "especificacion": "1,15 a 1,18 a 20 °C (100 g/L)", "min": 1.15, "max": 1.18, "campo": None, "unidad": ""},
    {"requisito": "Presentación", "especificacion": "", "min": None, "max": None, "campo": None, "unidad": ""},
    {"requisito": "Otros", "especificacion": "", "min": None, "max": None, "campo": None, "unidad": ""},
)
# Materias primas del formulario → palabra con la que aparecen en el stock.
MATERIAS_PRIMAS = (("Cloruro de sodio", "sal"), ("Agua", None), ("Hidróxido de sodio", "soda"),
                   ("Ácido clorhídrico", "clorhidrico"), ("Carbonato de sodio", "carbonato"),
                   ("Metabisulfito de sodio", "sulfito"), ("Otros", None))
PROCESO = ("Tratamiento de salmuera", "Filtración", "Intercambio iónico", "Electrólisis", "Absorción de cloro", "Temperatura", "Otros")
SALIDAS = ("Especificación del producto", "Características físico-químicas", "Parámetros de fabricación",
           "Criterios de aceptación", "Método de control", "Condiciones de almacenamiento", "Envasado / presentación",
           "Instrucciones de producción", "Otros")
REVISION_ASPECTOS = ("Requisitos del producto", "Materias primas", "Parámetros del proceso", "Factibilidad productiva",
                     "Criterios de aceptación", "Controles de calidad", "Almacenamiento / presentación", "Otros")
IMPACTO_ASPECTOS = ("Materias primas", "Tratamiento de salmuera", "Filtración", "Intercambio iónico", "Electrolizador",
                    "Generación / absorción de cloro", "Concentración del producto", "Calidad del producto",
                    "Equipos / instalaciones", "Parámetros del proceso", "Almacenamiento", "Envasado / despacho",
                    "Documentación", "Cliente", "Requisitos legales", "Otros")
CONTROLES_CAMBIO = ("¿Requiere revisión?", "¿Requiere verificación?", "¿Requiere validación?", "¿Requiere actualización documental?")
FIRMANTES = {"planta": "Responsable de Planta", "calidad": "Responsable de Control de Calidad", "gerencia": "Gerencia General"}
FIRMANTES_CAMBIO = {"planta": "Responsable de Planta", "calidad": "Control de Calidad"}
NO_APLICA = "No aplica"


# ------------------------------------------------------------------ utilidades


def _j(raw: str | None, default: Any) -> Any:
    try:
        v = json.loads(raw or "")
    except ValueError:
        return default
    return v if isinstance(v, type(default)) else default


def _txt(v: Any, largo: int | None = None) -> str:
    s = str(v or "").strip()
    return s[:largo] if largo else s


def _num(v: float | None) -> str:
    if v is None:
        return ""
    txt = f"{v:,.2f}".rstrip("0").rstrip(".")
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def datos(d: DesarrolloProduccion | DesarrolloCambio | None) -> dict[str, Any]:
    return _j(d.datos, {}) if d is not None else {}


def firmas(d: DesarrolloProduccion | DesarrolloCambio | None) -> dict[str, Any]:
    return _j(d.firmas, {}) if d is not None else {}


def firma_texto(f: dict[str, Any] | None) -> str:
    if not f:
        return "Pendiente de firma"
    return f"Firmado en el sistema por {f.get('nombre')} · {fecha_local(datetime.fromisoformat(f['at']))}"


def periodo(d: DesarrolloProduccion) -> tuple[date, date]:
    return d.prueba_desde, d.prueba_hasta or date.today()


# ------------------------------------------------------------------ evidencia del sistema


def _rango(valores: list[float], unidad: str = "") -> str:
    vs = [v for v in valores if v is not None]
    if not vs:
        return ""
    u = f" {unidad}" if unidad else ""
    if min(vs) == max(vs):
        return f"{_num(vs[0])}{u} ({len(vs)} registros)"
    return f"{_num(min(vs))} a {_num(max(vs))}{u}, promedio {_num(mean(vs))}{u} ({len(vs)} registros)"


def _salmuera(desde: date, hasta: date) -> list[SalmueraRegistro]:
    return list(db.session.scalars(select(SalmueraRegistro).where(
        SalmueraRegistro.fecha_iso >= desde.isoformat(), SalmueraRegistro.fecha_iso <= hasta.isoformat())))


def _reactor(desde: date, hasta: date) -> list[ReactorRegistro]:
    return list(db.session.scalars(select(ReactorRegistro).where(
        ReactorRegistro.fecha_iso >= desde.isoformat(), ReactorRegistro.fecha_iso <= hasta.isoformat())))


def _agua(desde: date, hasta: date) -> list[AguaRegistro]:
    return list(db.session.scalars(select(AguaRegistro).where(
        AguaRegistro.fecha_iso >= desde.isoformat(), AguaRegistro.fecha_iso <= hasta.isoformat())))


def _analisis_8hs(desde: date, hasta: date) -> list[SalmueraAnalisis8hs]:
    fin = (hasta + timedelta(days=1)).isoformat()
    return list(db.session.scalars(select(SalmueraAnalisis8hs).where(
        SalmueraAnalisis8hs.fecha_hora_iso >= desde.isoformat(), SalmueraAnalisis8hs.fecha_hora_iso < fin)))


def evidencia(d: DesarrolloProduccion) -> dict[str, Any]:
    """Todo lo que el sistema ya registró en el período de pruebas, listo para las tres hojas."""
    from app.services import sgi_procedimiento_service as proc

    desde, hasta = periodo(d)
    sal, rea, agua, a8 = _salmuera(desde, hasta), _reactor(desde, hasta), _agua(desde, hasta), _analisis_8hs(desde, hasta)
    fin = (hasta + timedelta(days=1)).isoformat()
    lotes = sorted({lo for lo in db.session.scalars(select(ShiftSession.lote_produccion).where(
        ShiftSession.started_at_iso >= desde.isoformat(), ShiftSession.started_at_iso < fin,
        ShiftSession.lote_produccion.isnot(None))) if lo} | {r.lote for r in [*sal, *rea, *agua] if (r.lote or "").startswith("P")})
    ingresos = list(db.session.scalars(select(IngresoStock).where(
        IngresoStock.categoria == "materia_prima", IngresoStock.fecha >= desde.isoformat(), IngresoStock.fecha <= hasta.isoformat()
    ).order_by(IngresoStock.fecha)))
    consumos = db.session.execute(select(ConsumoStock.producto, func.sum(ConsumoStock.cantidad), func.count()).where(
        ConsumoStock.categoria == "materia_prima", ConsumoStock.fecha >= desde.isoformat(), ConsumoStock.fecha <= hasta.isoformat()
    ).group_by(ConsumoStock.producto).order_by(ConsumoStock.producto)).all()
    nombres = {re.sub(r"\s*\(.*\)\s*$", "", r.operador or "").strip() for r in [*sal, *rea, *agua, *a8]} - {""}
    usuarios = {u.username.lower(): (u.nombre_completo or "").strip() for u in db.session.scalars(
        select(User).where(func.lower(User.username).in_([n.lower() for n in nombres])))}
    operadores = sorted({usuarios.get(n.lower()) or n for n in nombres}, key=str.lower)
    electrolizadores = sorted({int(r.electrolizador) for r in sal if r.electrolizador})

    resultados = []
    for p in PRODUCTO:
        vals = [getattr(r, p["campo"]) for r in sal if getattr(r, p["campo"]) is not None] if p["campo"] else []
        conforme = None
        if vals and (p["min"] is not None or p["max"] is not None):
            fuera = [v for v in vals if (p["min"] is not None and v < p["min"]) or (p["max"] is not None and v > p["max"])]
            conforme = not fuera
            detalle = _rango(vals, p["unidad"]) + (f"; {len(fuera)} fuera de especificación" if fuera else "")
        else:
            detalle = _rango(vals, p["unidad"])
        resultados.append({**p, "resultado": detalle, "conforme": conforme,
                           "fuente": f"Registros de salmuera ({len(vals)})" if vals else ""})

    mp = []
    for nombre, clave in MATERIAS_PRIMAS:
        if clave is None:
            fuente = (f"Agua tratada: dureza {_rango([r.dureza for r in agua])}" if nombre == "Agua" and agua else "")
        else:
            ing = [i for i in ingresos if clave in (i.producto or "").lower()]
            fuente = "; ".join(f"{i.producto} {i.marca}, lote {i.lote} ({fecha_dmy(parse_fecha(i.fecha))})" for i in ing[:6])
            if len(ing) > 6:
                fuente += f" y {len(ing) - 6} ingresos más"
            if not ing:  # sin ingresos en el período: la que se estaba usando es la del último ingreso
                previo = db.session.scalar(select(IngresoStock).where(
                    IngresoStock.categoria == "materia_prima", IngresoStock.fecha < desde.isoformat(),
                    func.lower(IngresoStock.producto).contains(clave)).order_by(IngresoStock.fecha.desc(), IngresoStock.id.desc()).limit(1))
                if previo is not None:
                    fuente = (f"{previo.producto} {previo.marca}, lote {previo.lote} "
                              f"(último ingreso, {fecha_dmy(parse_fecha(previo.fecha))})")
        mp.append({"materia_prima": nombre, "fuente": fuente})

    proceso = {
        "Tratamiento de salmuera": "; ".join(x for x in (
            f"concentración {_rango([r.sal_conc for r in sal], 'g/L')}" if any(r.sal_conc for r in sal) else "",
            f"pH {_rango([r.sal_ph for r in sal])}" if any(r.sal_ph for r in sal) else "",
            f"dureza (8 hs) {_rango([r.dureza_salmuera for r in a8])}" if any(r.dureza_salmuera is not None for r in a8) else "",
            f"pH reactor {_rango([r.ph for r in rea])}" if any(r.ph for r in rea) else "",
        ) if x),
        "Filtración": "",
        "Intercambio iónico": f"dureza del agua {_rango([r.dureza for r in agua])}" if agua else "",
        "Electrólisis": "; ".join(x for x in (
            f"voltaje {_rango([r.voltaje_total for r in sal], 'V')}" if any(r.voltaje_total for r in sal) else "",
            f"amperaje {_rango([r.amperaje for r in sal], 'A')}" if any(r.amperaje for r in sal) else "",
        ) if x),
        "Absorción de cloro": f"concentración del hipoclorito {_rango([r.hipo_conc for r in sal], 'g/L')}" if any(r.hipo_conc for r in sal) else "",
        "Temperatura": "; ".join(x for x in (
            f"salmuera {_rango([r.sal_temp for r in sal], '°C')}" if any(r.sal_temp for r in sal) else "",
            f"reactor {_rango([r.temperatura for r in rea], '°C')}" if any(r.temperatura for r in rea) else "",
        ) if x),
        "Otros": "",
    }

    from app.models.sgi import SgiDocumento

    docs = []
    for codigo in ("QDV-PO-04", "QDV-PO-05", "QDV-PO-06"):
        doc = db.session.scalar(select(SgiDocumento).where(SgiDocumento.codigo == codigo).limit(1))
        rev = proc.revision_vigente_aprobada(doc) if doc is not None else None
        docs.append(f"{codigo} {doc.titulo.capitalize()} {rev.revision_label}" if rev is not None else codigo)

    recursos = {
        "personal": ", ".join(operadores),
        "equipos": ("Electrolizadores " + ", ".join(str(e) for e in electrolizadores) + "; " if electrolizadores else "")
                   + "planta de agua, reactor de salmuera, clarificador, filtros e intercambio iónico",
        "materias_primas": "; ".join(f"{p} {_num(c)} ({n} consumos)" for p, c, n in consumos),
        "ensayos": ", ".join(x for x in (
            f"{len(sal)} registros de salmuera / electrólisis" if sal else "", f"{len(rea)} del reactor" if rea else "",
            f"{len(agua)} de agua" if agua else "", f"{len(a8)} análisis de 8 hs" if a8 else "") if x),
        "documentacion": "; ".join(docs),
    }
    return {"desde": desde, "hasta": hasta, "lotes": lotes, "resultados": resultados, "materias_primas": mp,
            "proceso": proceso, "recursos": recursos, "hay_datos": bool(sal or rea or agua or a8)}


# ------------------------------------------------------------------ desarrollos


def listar() -> list[DesarrolloProduccion]:
    return list(db.session.scalars(select(DesarrolloProduccion).where(DesarrolloProduccion.activo.is_(True))
                                   .order_by(DesarrolloProduccion.numero.desc())))


def get(desarrollo_id: int) -> DesarrolloProduccion | None:
    d = db.session.get(DesarrolloProduccion, int(desarrollo_id))
    return d if d is not None and d.activo else None


def historial(d: DesarrolloProduccion, limit: int = 100) -> list[DesarrolloHistorial]:
    return list(db.session.scalars(select(DesarrolloHistorial).where(DesarrolloHistorial.desarrollo_id == d.id)
                                   .order_by(DesarrolloHistorial.created_at.desc(), DesarrolloHistorial.id.desc()).limit(limit)).unique())


def _log(d_id: int, user_id: int | None, detalle: str, cambio_id: int | None = None) -> None:
    db.session.add(DesarrolloHistorial(desarrollo_id=d_id, cambio_id=cambio_id, user_id=user_id, detalle=detalle[:4000]))


def _fecha(data: Any, clave: str, label: str, errores: list[str], obligatoria: bool = True) -> date | None:
    try:
        f = parse_fecha(data.get(clave))
    except ValueError:
        errores.append(f"{label}: fecha inválida, usá dd/mm/aaaa.")
        return None
    if f is None and obligatoria:
        errores.append(f"{label}: es obligatoria.")
    return f


def _cabecera(data: Any) -> tuple[dict[str, Any], list[str]]:
    errores: list[str] = []
    v = {
        "fecha_inicio": _fecha(data, "fecha_inicio", "Fecha de inicio", errores),
        "producto_proceso": _txt(data.get("producto_proceso"), 255),
        "tipo": _txt(data.get("tipo")),
        "motivo": _txt(data.get("motivo")),
        "prueba_desde": _fecha(data, "prueba_desde", "Período de pruebas desde", errores),
        "prueba_hasta": _fecha(data, "prueba_hasta", "Período de pruebas hasta", errores, obligatoria=False),
    }
    if not v["producto_proceso"]:
        errores.append("Producto / proceso: es obligatorio.")
    if v["tipo"] not in TIPOS:
        errores.append("Tipo: elegí «Nuevo desarrollo» o «Modificación».")
    if not v["motivo"]:
        errores.append("Motivo / necesidad: es obligatorio.")
    if v["prueba_desde"] and v["prueba_hasta"] and v["prueba_hasta"] < v["prueba_desde"]:
        errores.append("El período de pruebas termina antes de empezar.")
    return v, errores


def _hojas(data: Any) -> dict[str, Any]:
    """Lo que se completa a mano en las tres hojas (vacío = pendiente)."""
    g = lambda k: _txt(data.get(k))  # noqa: E731
    out: dict[str, Any] = {
        "planificacion": [{k: g(f"etapa_{i}_{k}") for k in ("responsable", "fecha_prevista", "fecha_realizada", "estado")}
                          for i in range(len(ETAPAS))],
        "recursos": {k: g(f"recurso_{k}") for k in RECURSOS},
        "criterios": g("criterios"), "observaciones_01": g("observaciones_01"),
        "producto": [{k: g(f"producto_{i}_{k}") for k in ("especificacion", "fuente", "conforme")} for i in range(len(PRODUCTO))],
        "materias_primas": [{k: g(f"mp_{i}_{k}") for k in ("requisito", "fuente", "conforme")} for i in range(len(MATERIAS_PRIMAS))],
        "proceso": [{k: g(f"proceso_{i}_{k}") for k in ("valor", "fuente")} for i in range(len(PROCESO))],
        "otros_requisitos": [x for x in OTROS_REQUISITOS if g(f"otro_{x}")],
        "otros_detalle": g("otros_detalle"),
        "salidas": [{k: g(f"salida_{i}_{k}") for k in ("documento", "aprobada")} for i in range(len(SALIDAS))],
        "resultado_final": g("resultado_final"), "salidas_cumplen": g("salidas_cumplen"),
        "observaciones_02": g("observaciones_02"),
        "revision": [{k: g(f"rev_{i}_{k}") for k in ("conforme", "observaciones")} for i in range(len(REVISION_ASPECTOS))],
        "metodos": [x for x in METODOS_VERIFICACION if g(f"metodo_{x}")], "metodo_otro": g("metodo_otro"),
        "verificacion": [{k: g(f"verif_{i}_{k}") for k in ("resultado", "conforme")} for i in range(len(PRODUCTO))],
        "informe": g("informe"), "verificacion_resultado": g("verificacion_resultado"),
        "observaciones_verif": g("observaciones_verif"),
        "requiere_validacion": g("requiere_validacion"), "justificacion": g("justificacion"),
        "metodo_validacion": g("metodo_validacion"), "resultado_validacion": g("resultado_validacion"),
        "cumple_uso": g("cumple_uso"),
        "resultado_aprobacion": g("resultado_aprobacion"), "observaciones_aprobacion": g("observaciones_aprobacion"),
        "fecha_liberacion": g("fecha_liberacion"),
    }
    for lista in ("producto", "materias_primas", "salidas"):
        for fila in out[lista]:
            if "conforme" in fila:
                fila["conforme"] = "Sí" if fila["conforme"] else ""
            if "aprobada" in fila:
                fila["aprobada"] = "Sí" if fila["aprobada"] else ""
    return out


def _numero(model: Any) -> int:
    return (db.session.scalar(select(func.max(model.numero))) or 0) + 1


def crear(data: Any, user_id: int | None) -> tuple[DesarrolloProduccion | None, list[str]]:
    v, errores = _cabecera(data)
    if errores:
        return None, errores
    d = DesarrolloProduccion(numero=_numero(DesarrolloProduccion), datos=json.dumps(_hojas({}), ensure_ascii=False), **v)
    db.session.add(d)
    db.session.flush()
    _log(d.id, user_id, f"Alta del desarrollo N° {d.numero}: {d.producto_proceso}")
    return d, []


def guardar(d: DesarrolloProduccion, data: Any, user_id: int | None) -> tuple[list[str], bool]:
    """(errores, cambió). Si cambió algo y había firmas, se anulan."""
    v, errores = _cabecera(data)
    for k in ("fecha_liberacion",):
        if _txt(data.get(k)):
            try:
                parse_fecha(data.get(k))
            except ValueError:
                errores.append("Fecha de liberación: fecha inválida, usá dd/mm/aaaa.")
    if errores:
        return errores, False
    nuevos = _hojas(data)
    cambios = [k for k, val in v.items() if getattr(d, k) != val]
    if nuevos != datos(d):
        cambios.append("hojas")
    if not cambios:
        return [], False
    for k, val in v.items():
        setattr(d, k, val)
    d.datos = json.dumps(nuevos, ensure_ascii=False)
    _log(d.id, user_id, "Modificó: " + ", ".join("contenido de las hojas" if c == "hojas" else c.replace("_", " ") for c in cambios))
    if firmas(d):
        d.firmas = "{}"
        _log(d.id, user_id, "Firmas anuladas porque se modificó el desarrollo: tienen que volver a firmar.")
    return [], True


def faltantes(d: DesarrolloProduccion) -> list[str]:
    """Lo que falta completar para poder firmar la liberación: ningún campo de las hojas puede quedar vacío."""
    h = datos(d)
    ev = evidencia(d)
    falta: list[str] = []
    for i, e in enumerate(h.get("planificacion", [])):
        if not all(e.get(k) for k in ("responsable", "fecha_prevista", "estado")):
            falta.append(f"03_01 etapa {i + 1} ({ETAPAS[i]})")
        elif e.get("estado") == "Realizada" and not e.get("fecha_realizada"):
            falta.append(f"03_01 fecha realizada de la etapa {i + 1}")
    for k in RECURSOS:
        if not (h.get("recursos", {}).get(k) or ev["recursos"].get(k)):
            falta.append(f"03_01 recursos: {RECURSOS_LABELS[k]}")
    for k, label in (("criterios", "03_01 criterios de aceptación"), ("resultado_final", "03_02 resultado final"),
                     ("salidas_cumplen", "03_02 ¿las salidas cumplen las entradas?"),
                     ("verificacion_resultado", "03_03 resultado de la verificación"),
                     ("requiere_validacion", "03_03 ¿requiere validación?"),
                     ("resultado_aprobacion", "03_03 resultado final de la aprobación"),
                     ("fecha_liberacion", "03_03 fecha de liberación")):
        if not h.get(k):
            falta.append(label)
    if h.get("requiere_validacion") == "Sí":
        for k, label in (("metodo_validacion", "método de validación"), ("resultado_validacion", "resultado de la validación"),
                         ("cumple_uso", "¿cumple el uso previsto?")):
            if not h.get(k):
                falta.append(f"03_03 {label}")
    elif h.get("requiere_validacion") == "No" and not h.get("justificacion"):
        falta.append("03_03 justificación de por qué no requiere validación")
    for i, fila in enumerate(h.get("revision", [])):
        if not fila.get("conforme") and REVISION_ASPECTOS[i] != "Otros":
            falta.append(f"03_03 revisión: {REVISION_ASPECTOS[i]}")
    if not (h.get("metodos") or h.get("metodo_otro")):
        falta.append("03_03 método de verificación")
    return falta


def puede_firmar(d: DesarrolloProduccion, user: User | None, rol: str) -> bool:
    from app.user_roles import user_is_responsable_laboratorio

    if user is None or rol not in FIRMANTES or rol in firmas(d):
        return False
    if rol == "calidad":
        return user_is_responsable_laboratorio(user) or bool(user.is_admin)
    return bool(user.is_admin)


def firmar(d: DesarrolloProduccion, user: User, rol: str) -> str:
    from app.auth_utils import user_display_name

    if not puede_firmar(d, user, rol):
        raise ValueError("No te corresponde esa firma o ya está firmada.")
    falta = faltantes(d)
    if falta:
        raise ValueError("Antes de firmar completá: " + "; ".join(falta[:8]) + (" …" if len(falta) > 8 else "."))
    f = firmas(d)
    f[rol] = {"user_id": int(user.id), "nombre": user_display_name(user), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    d.firmas = json.dumps(f, ensure_ascii=False)
    _log(d.id, int(user.id), f"Firmó {user_display_name(user)} como {FIRMANTES[rol]}")
    return f"Firmaste el desarrollo N° {d.numero} como {FIRMANTES[rol]}."


def baja(d: DesarrolloProduccion, user_id: int | None) -> None:
    d.activo = False
    _log(d.id, user_id, f"Baja del desarrollo N° {d.numero}")


# ------------------------------------------------------------------ cambios (03_04)


def cambios(d: DesarrolloProduccion | None = None) -> list[DesarrolloCambio]:
    q = select(DesarrolloCambio).where(DesarrolloCambio.activo.is_(True))
    if d is not None:
        q = q.where(DesarrolloCambio.desarrollo_id == d.id)
    return list(db.session.scalars(q.order_by(DesarrolloCambio.numero.desc())).unique())


def get_cambio(cambio_id: int) -> DesarrolloCambio | None:
    c = db.session.get(DesarrolloCambio, int(cambio_id))
    return c if c is not None and c.activo else None


def _datos_cambio(data: Any) -> tuple[dict[str, Any], date | None, list[str]]:
    errores: list[str] = []
    fecha = _fecha(data, "fecha", "Fecha", errores)
    v = {
        "producto_proceso": _txt(data.get("producto_proceso"), 255),
        "descripcion": _txt(data.get("descripcion")), "motivo": _txt(data.get("motivo")),
        "impacto": [{"afecta": _txt(data.get(f"imp_{i}")), "observaciones": _txt(data.get(f"imp_{i}_obs"))}
                    for i in range(len(IMPACTO_ASPECTOS))],
        "controles": [_txt(data.get(f"control_{i}")) for i in range(len(CONTROLES_CAMBIO))],
        "resultado": _txt(data.get("resultado")),
    }
    for k, label in (("producto_proceso", "Producto / proceso"), ("descripcion", "Descripción del cambio"), ("motivo", "Motivo del cambio")):
        if not v[k]:
            errores.append(f"{label}: es obligatorio.")
    for i, fila in enumerate(v["impacto"]):
        if fila["afecta"] not in ("Afecta", "No afecta"):
            errores.append(f"Evaluación de impacto: marcá si afecta o no afecta a {IMPACTO_ASPECTOS[i]}.")
        elif fila["afecta"] == "Afecta" and not fila["observaciones"]:
            errores.append(f"Evaluación de impacto: explicá en observaciones cómo afecta a {IMPACTO_ASPECTOS[i]}.")
    for i, c in enumerate(v["controles"]):
        if c not in SI_NO:
            errores.append(f"Controles requeridos: respondé «{CONTROLES_CAMBIO[i]}».")
    if v["resultado"] not in RESULTADOS_CAMBIO:
        errores.append("Resultado: indicá si el cambio queda aprobado para su implementación.")
    return v, fecha, errores


def crear_cambio(d: DesarrolloProduccion, data: Any, user_id: int | None) -> tuple[DesarrolloCambio | None, list[str]]:
    v, fecha, errores = _datos_cambio(data)
    if errores:
        return None, errores
    c = DesarrolloCambio(numero=_numero(DesarrolloCambio), desarrollo_id=d.id, fecha=fecha, datos=json.dumps(v, ensure_ascii=False))
    db.session.add(c)
    db.session.flush()
    _log(d.id, user_id, f"Alta del cambio N° {c.numero}: {v['descripcion'][:200]}", c.id)
    return c, []


def guardar_cambio(c: DesarrolloCambio, data: Any, user_id: int | None) -> list[str]:
    v, fecha, errores = _datos_cambio(data)
    if errores:
        return errores
    if v == datos(c) and fecha == c.fecha:
        return []
    c.datos, c.fecha = json.dumps(v, ensure_ascii=False), fecha
    _log(c.desarrollo_id, user_id, f"Modificó el cambio N° {c.numero}", c.id)
    if firmas(c):
        c.firmas = "{}"
        _log(c.desarrollo_id, user_id, f"Firmas del cambio N° {c.numero} anuladas: tienen que volver a firmar.", c.id)
    return []


def puede_firmar_cambio(c: DesarrolloCambio, user: User | None, rol: str) -> bool:
    if rol not in FIRMANTES_CAMBIO:
        return False
    return puede_firmar(c, user, rol)  # mismas reglas: planta = admin, calidad = laboratorio o admin


def firmar_cambio(c: DesarrolloCambio, user: User, rol: str) -> str:
    from app.auth_utils import user_display_name

    if not puede_firmar_cambio(c, user, rol):
        raise ValueError("No te corresponde esa firma o ya está firmada.")
    f = firmas(c)
    f[rol] = {"user_id": int(user.id), "nombre": user_display_name(user), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    c.firmas = json.dumps(f, ensure_ascii=False)
    _log(c.desarrollo_id, int(user.id), f"Firmó el cambio N° {c.numero} {user_display_name(user)} como {FIRMANTES_CAMBIO[rol]}", c.id)
    return f"Firmaste el cambio N° {c.numero} como {FIRMANTES_CAMBIO[rol]}."


def estado(d: DesarrolloProduccion) -> str:
    h, f = datos(d), firmas(d)
    if "planta" in f and "calidad" in f:
        return {"NO APROBADO": "No aprobado"}.get(h.get("resultado_aprobacion"), "Liberado")
    return "En desarrollo"


def labels_context() -> dict[str, Any]:
    return {
        "dd_registros": REGISTROS, "dd_revision": REVISION, "dd_tipos": TIPOS, "dd_etapas": ETAPAS,
        "dd_estados_etapa": ESTADOS_ETAPA, "dd_si_no": SI_NO, "dd_resultados_aprobacion": RESULTADOS_APROBACION,
        "dd_resultados_cambio": RESULTADOS_CAMBIO, "dd_metodos": METODOS_VERIFICACION, "dd_otros_requisitos": OTROS_REQUISITOS,
        "dd_recursos": RECURSOS, "dd_recursos_labels": RECURSOS_LABELS, "dd_producto": PRODUCTO,
        "dd_materias_primas": MATERIAS_PRIMAS, "dd_proceso": PROCESO, "dd_salidas": SALIDAS,
        "dd_revision_aspectos": REVISION_ASPECTOS, "dd_impacto": IMPACTO_ASPECTOS, "dd_controles": CONTROLES_CAMBIO,
        "dd_firmantes": FIRMANTES, "dd_firmantes_cambio": FIRMANTES_CAMBIO, "dd_datos": datos, "dd_firmas": firmas,
        "dd_firma_texto": firma_texto, "dd_estado": estado, "fecha_dmy": fecha_dmy, "fecha_local": fecha_local,
        "no_aplica": NO_APLICA, "hoy": date.today(),
    }
