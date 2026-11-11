"""Detección de posibles datos falsos: aprende del historial y marca lo que no encaja."""
import random
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services import datos_sospechosos_service as svc

SERIE = {"clave": "reactor", "nombre": "Reactor", "campos": ("densidad", "concentracion_tabla", "ph"),
         "lab": ("densidad", "concentracion_tabla", "ph")}
T0 = datetime(2026, 9, 1)


class _Nombres:
    def de(self, operador):
        return operador, ""


def _momento(r):
    return r.momento


def _fila(i, dens, operador="ana", conc=None, ph=None):
    return SimpleNamespace(momento=T0 + timedelta(hours=2 * i), operador=operador, densidad=dens,
                           concentracion_tabla=conc if conc is not None else round(2.5 * dens - 2670, 1),
                           ph=ph if ph is not None else round(11 + random.random(), 2))


def _historial():
    random.seed(1)
    return [_fila(i, 1180 + random.random() * 28) for i in range(300)]


def test_aprende_relacion_y_marca_lo_que_no_cierra():
    hist = _historial()
    modelo = svc.aprender(SERIE, hist, _momento)
    assert any(r["x"] == "densidad" and r["y"] == "concentracion_tabla" for r in modelo["relaciones"])
    assert modelo["copia_base"] < 0.05
    dia = [_fila(301, 1200), _fila(302, 1205, conc=290.0, operador="beto")]
    out = svc.evaluar(SERIE, modelo, dia, hist[-1], _momento, _Nombres(), [])
    assert [(i["persona"], i["tipo"]) for i in out] == [("beto", "No cierra")]


def test_copia_del_anterior_y_turno_sin_variacion():
    hist = _historial()
    modelo = svc.aprender(SERIE, hist, _momento)
    a = _fila(301, 1200, ph=11.3)
    copias = [_fila(301 + k, 1200, operador="beto", ph=11.3) for k in range(1, 4)]
    out = svc.evaluar(SERIE, modelo, [a, *copias], hist[-1], _momento, _Nombres(),
                      [(a.momento, a.momento + timedelta(hours=8))])
    tipos = [i["tipo"] for i in out if i["persona"] == "beto"]
    assert tipos.count("Copia del anterior") == 3
    assert "Sin variación en el turno" in tipos


def test_repeticion_por_persona():
    hist = _historial()
    for k in range(20):
        hist.append(_fila(400 + k, 1200, operador="beto", ph=11.3))
    filas = {p["persona"]: p for p in svc.repeticion_por_persona(SERIE, hist, _momento, _Nombres())}
    assert filas["beto"]["alerta"] and not filas["ana"]["alerta"]
