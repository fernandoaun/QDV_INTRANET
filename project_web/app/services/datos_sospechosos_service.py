"""Posibles datos falsos en los análisis de planta (sección del informe diario de análisis).

El sistema aprende de los últimos 60 días cómo se comportan los valores de cada análisis y vuelve a aprender
todos los días, así que las reglas se ajustan solas a medida que hay más datos:

- el rango habitual de cada campo;
- cuántas veces es normal que un análisis repita exactamente los valores del anterior;
- qué campos se mueven juntos (correlación |r| >= 0,6), con la recta que los relaciona y su dispersión.

Con eso marca en el día del informe: análisis copiados del anterior, valores que no cambian en todo el turno
cuando normalmente cambian, valores que no cierran con los que se relacionan y valores fuera de lo habitual.
Además compara, por persona, cuántas veces repite valores frente al resto del equipo en los últimos 30 días.
Son indicios para revisar con el personal, no pruebas.
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.models import AguaRegistro, ReactorRegistro, SalmueraAnalisis8hs, SalmueraRegistro

DIAS_APRENDIZAJE = 60
DIAS_PERSONAS = 30
MIN_DATOS = 50
R_MIN = 0.6
SIGMAS = 4.0
# Una copia del análisis anterior solo cuenta si el anterior es de menos de 12 h.
VENTANA_COPIA = timedelta(hours=12)

ETIQUETAS = {
    "amperaje": "amperaje", "voltaje_total_trafo": "voltaje del trafo", "caudal_agua_l_h": "caudal de agua",
    "caudal_salmuera_l_h": "caudal de salmuera", "hipo_conc": "concentración de hipoclorito",
    "hipo_exceso_soda": "exceso de soda", "sal_temp": "temperatura de salmuera", "sal_conc": "concentración de salmuera",
    "sal_ph": "pH de salmuera", "soda_conc": "concentración de soda", "declor_ph": "pH de declorado",
    "ph": "pH", "temperatura": "temperatura", "densidad": "densidad", "concentracion_tabla": "concentración",
    "exceso_naoh": "exceso de NaOH", "exceso_na2co3": "exceso de Na2CO3", "dureza": "dureza",
    "dureza_salmuera": "dureza de salmuera", "cloro_libre_salmuera": "cloro libre",
}


def series() -> list[dict[str, Any]]:
    """Cada serie de análisis: campos medidos y, de ellos, los de laboratorio (los que se copian)."""
    out = []
    for e in (2, 3):
        out.append({"clave": f"salmuera_e{e}", "nombre": f"Hipoclorito E{e}", "modelo": SalmueraRegistro,
                    "filtro": SalmueraRegistro.electrolizador == e,
                    "campos": ("amperaje", "voltaje_total_trafo", "caudal_agua_l_h", "caudal_salmuera_l_h", "hipo_conc",
                               "hipo_exceso_soda", "sal_temp", "sal_conc", "sal_ph", "soda_conc", "declor_ph"),
                    "lab": ("hipo_conc", "hipo_exceso_soda", "sal_conc", "sal_ph", "soda_conc", "declor_ph"),
                    "marcha": "amperaje"})
    out += [
        {"clave": "reactor", "nombre": "Reactor", "modelo": ReactorRegistro,
         "campos": ("ph", "temperatura", "densidad", "concentracion_tabla", "exceso_naoh", "exceso_na2co3"),
         "lab": ("ph", "temperatura", "densidad", "concentracion_tabla", "exceso_naoh", "exceso_na2co3")},
        {"clave": "agua", "nombre": "Agua", "modelo": AguaRegistro, "campos": ("temperatura", "dureza"),
         "lab": ("temperatura", "dureza")},
        {"clave": "analisis_8hs", "nombre": "Análisis de 8 hs", "modelo": SalmueraAnalisis8hs,
         "campos": ("dureza_salmuera", "cloro_libre_salmuera"), "lab": ("dureza_salmuera", "cloro_libre_salmuera")},
    ]
    return out


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _pct(vals: list[float], p: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(round(p / 100 * (len(s) - 1)))))]


def _fmt(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _es_copia(r: Any, prev: Any, momento: Any, lab: tuple[str, ...]) -> bool:
    if prev is None or momento(r) - momento(prev) > VENTANA_COPIA:
        return False
    vals = [(_num(getattr(r, c)), _num(getattr(prev, c))) for c in lab]
    vals = [(a, b) for a, b in vals if a is not None and b is not None]
    return len(vals) >= 2 and all(a == b for a, b in vals)


def en_marcha(serie: dict[str, Any], modelo: dict[str, Any], r: Any) -> bool:
    """Con el electrolizador apagado o en arranque las relaciones de proceso no valen: se miran solo en marcha."""
    campo, umbral = serie.get("marcha"), modelo.get("umbral_marcha")
    if not campo or umbral is None:
        return True
    v = _num(getattr(r, campo))
    return v is not None and v >= umbral


def aprender(serie: dict[str, Any], todas: list[Any], momento: Any) -> dict[str, Any]:
    """Rangos, tasa normal de copias y relaciones entre campos a partir del historial."""
    m: dict[str, Any] = {"n": 0, "rangos": {}, "repite": {}, "relaciones": [], "copia_base": None, "umbral_marcha": None}
    if serie.get("marcha"):
        vals = [v for r in todas if (v := _num(getattr(r, serie["marcha"]))) is not None]
        if vals:
            m["umbral_marcha"] = 0.5 * st.median(vals)
    filas = [r for r in todas if en_marcha(serie, m, r)]
    m["n"] = len(filas)
    copias = [_es_copia(b, a, momento, serie["lab"]) for a, b in zip(todas, todas[1:])]
    m["copia_base"] = sum(copias) / len(copias) if copias else None
    if len(filas) < MIN_DATOS:
        return m
    for c in serie["campos"]:
        vals = [v for r in filas if (v := _num(getattr(r, c))) is not None]
        if len(vals) >= MIN_DATOS:
            m["rangos"][c] = (_pct(vals, 0.5), _pct(vals, 99.5), _pct(vals, 2), _pct(vals, 98))
        pares = [(_num(getattr(a, c)), _num(getattr(b, c))) for a, b in zip(filas, filas[1:])]
        pares = [(x, y) for x, y in pares if x is not None and y is not None]
        if pares:
            m["repite"][c] = sum(x == y for x, y in pares) / len(pares)
    campos = [c for c in serie["campos"] if c in m["rangos"]]
    for i, x in enumerate(campos):
        for y in campos[i + 1:]:
            lx, ly = m["rangos"][x], m["rangos"][y]
            pts = [(a, b) for r in filas if (a := _num(getattr(r, x))) is not None and (b := _num(getattr(r, y))) is not None
                   and lx[2] <= a <= lx[3] and ly[2] <= b <= ly[3]]
            if len(pts) < MIN_DATOS:
                continue
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            try:
                r = st.correlation(xs, ys)
                pend, orig = st.linear_regression(xs, ys)
            except st.StatisticsError:
                continue
            if abs(r) < R_MIN:
                continue
            res = [b - (orig + pend * a) for a, b in pts]
            sigma = 1.4826 * st.median([abs(e - st.median(res)) for e in res])
            if sigma > 0:
                m["relaciones"].append({"x": x, "y": y, "r": r, "pend": pend, "orig": orig, "sigma": sigma})
    return m


def _indicio(r: Any, serie: dict[str, Any], momento: Any, nombres: Any, tipo: str, peso: int, texto: str) -> dict[str, Any]:
    return {"momento": momento(r), "persona": nombres.de(r.operador)[0], "analisis": serie["nombre"],
            "tipo": tipo, "peso": peso, "texto": texto}


def evaluar(serie: dict[str, Any], modelo: dict[str, Any], filas: list[Any], previa: Any, momento: Any,
            nombres: Any, turnos: list[tuple[datetime, datetime]]) -> list[dict[str, Any]]:
    """Indicios en los análisis del día según lo aprendido."""
    out: list[dict[str, Any]] = []
    base = modelo["copia_base"]
    prev = previa
    for r in filas:
        if base is not None and base < 0.15 and _es_copia(r, prev, momento, serie["lab"]):
            campos = ", ".join(ETIQUETAS.get(c, c) for c in serie["lab"] if _num(getattr(r, c)) is not None)
            out.append(_indicio(r, serie, momento, nombres, "Copia del anterior", 3,
                                f"mismos valores que el análisis de las {momento(prev).strftime('%H:%M')} en {campos}; "
                                f"pasa normalmente en el {round(100 * base)} % de los análisis"))
        prev = r
        if modelo["n"] < MIN_DATOS or not en_marcha(serie, modelo, r):
            continue
        no_cierra = []
        for rel in modelo["relaciones"]:
            a, b = _num(getattr(r, rel["x"])), _num(getattr(r, rel["y"]))
            lx = modelo["rangos"][rel["x"]]
            if a is None or b is None or not lx[2] <= a <= lx[3]:
                continue
            esperado = rel["orig"] + rel["pend"] * a
            if abs(b - esperado) > SIGMAS * rel["sigma"]:
                no_cierra.append(f"{ETIQUETAS.get(rel['y'], rel['y'])} {_fmt(b)} con {ETIQUETAS.get(rel['x'], rel['x'])} "
                                 f"{_fmt(a)} (lo esperable, alrededor de {_fmt(esperado)})")
        if no_cierra:
            out.append(_indicio(r, serie, momento, nombres, "No cierra", 2,
                                "valores que no se corresponden entre sí: " + "; ".join(no_cierra)
                                + f". Aprendido de {modelo['n']} análisis en marcha"))
        fuera = []
        for c, (lo, hi, _p2, _p98) in modelo["rangos"].items():
            v = _num(getattr(r, c))
            margen = 0.1 * (hi - lo)
            if v is not None and (v < lo - margen or v > hi + margen):
                fuera.append(f"{ETIQUETAS.get(c, c)} {_fmt(v)} (habitual {_fmt(lo)} a {_fmt(hi)})")
        if fuera:
            out.append(_indicio(r, serie, momento, nombres, "Fuera de lo habitual", 1,
                                "; ".join(fuera) + ". Puede ser un error de carga o un problema real de proceso"))
    # Un campo que no cambia en todo el turno cuando normalmente cambia.
    for desde, hasta in turnos:
        del_turno = [r for r in filas if desde <= momento(r) < hasta]
        if len(del_turno) < 3 or modelo["n"] < MIN_DATOS:
            continue
        for c in serie["lab"]:
            vals = [_num(getattr(r, c)) for r in del_turno]
            p = modelo["repite"].get(c)
            if None in vals or len(set(vals)) != 1 or p is None or p ** (len(vals) - 1) >= 0.02:
                continue
            out.append(_indicio(del_turno[-1], serie, momento, nombres, "Sin variación en el turno", 2,
                                f"{ETIQUETAS.get(c, c)} {_fmt(vals[0])} en los {len(vals)} análisis del turno; "
                                f"normalmente se repite solo el {round(100 * p)} % de las veces"))
    return out


def repeticion_por_persona(serie: dict[str, Any], filas: list[Any], momento: Any, nombres: Any) -> list[dict[str, Any]]:
    """Por persona, porcentaje de análisis copiados del anterior frente al resto del equipo."""
    cuenta: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for a, b in zip(filas, filas[1:]):
        p = nombres.de(b.operador)[0]
        cuenta[p][0] += 1
        cuenta[p][1] += int(_es_copia(b, a, momento, serie["lab"]))
    out = []
    total_n = sum(n for n, _ in cuenta.values())
    total_c = sum(c for _, c in cuenta.values())
    for p, (n, c) in cuenta.items():
        if n < 10:
            continue
        resto_n, resto_c = total_n - n, total_c - c
        resto = resto_c / resto_n if resto_n else None
        tasa = c / n
        out.append({"persona": p, "analisis": serie["nombre"], "n": n, "copias": c, "tasa": tasa, "resto": resto,
                    "alerta": n >= 15 and tasa >= 0.2 and (resto is None or tasa >= 2 * max(resto, 0.02))})
    return out


def analizar(dia_desde: datetime, dia_hasta: datetime, turnos: list[tuple[datetime, datetime]]) -> dict[str, Any]:
    from app.services.informe_analisis_service import _filas, _momento, _Nombres

    nombres = _Nombres()
    indicios: list[dict[str, Any]] = []
    personas: list[dict[str, Any]] = []
    aprendido: list[dict[str, Any]] = []
    for s in series():
        hist = _filas(s["modelo"], dia_desde - timedelta(days=DIAS_APRENDIZAJE), dia_desde, s.get("filtro"))
        modelo = aprender(s, hist, _momento)
        filas = _filas(s["modelo"], dia_desde, dia_hasta, s.get("filtro"))
        indicios += evaluar(s, modelo, filas, hist[-1] if hist else None, _momento, nombres, turnos)
        recientes = [r for r in hist if _momento(r) >= dia_desde - timedelta(days=DIAS_PERSONAS)] + filas
        personas += repeticion_por_persona(s, recientes, _momento, nombres)
        for rel in modelo["relaciones"]:
            aprendido.append({"analisis": s["nombre"], "x": ETIQUETAS.get(rel["x"], rel["x"]),
                              "y": ETIQUETAS.get(rel["y"], rel["y"]), "r": rel["r"], "n": modelo["n"]})
    indicios.sort(key=lambda i: (i["persona"].lower(), i["momento"]))
    resumen: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for i in indicios:
        resumen[i["persona"]][i["tipo"]] += 1
        resumen[i["persona"]]["_puntos"] += i["peso"]
    return {"indicios": indicios, "resumen": {p: dict(v) for p, v in resumen.items()},
            "personas": sorted(personas, key=lambda p: (not p["alerta"], -p["tasa"])), "aprendido": aprendido,
            "graves": sum(1 for i in indicios if i["peso"] >= 2)}
