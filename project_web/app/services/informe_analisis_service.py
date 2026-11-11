"""Informe diario de análisis por turno: qué análisis hizo cada persona y cuáles faltaron.

Se manda cada mañana (qdv-informe-analisis, 08:30 ART) con los tres turnos del día operativo anterior:
M (08 a 16), T (16 a 24) y N (00 a 08 del día siguiente). Por cada análisis se esperan tantos como
entran en la ventana del turno según su frecuencia (salmuera por electrolizador y reactor cada 2 h,
agua y análisis de 8 hs uno por turno, lavado de filtro uno por día), descontando las paradas de planta
declaradas en ese circuito.
"""
from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.constants import (
    AGUA_ANALYSIS_INTERVAL_SECONDS,
    ANALYSIS_INTERVAL_SECONDS,
    FILTRO_LAVADO_INTERVAL_SECONDS,
    SALMUERA_PANEL_ELECTROLIZADORES,
)
from app.extensions import db
from app.models import (
    AguaRegistro,
    DeadlineReminderSent,
    EmpleadoPersonal,
    FiltroLavadoRegistro,
    PlantStopEvent,
    ReactorRegistro,
    SalmueraAnalisis8hs,
    SalmueraRegistro,
    ShiftSession,
    User,
)
from app.services.deadline_alert_email_service import normalize_validate_email
from app.services.mail_service import enviar_mail, is_mail_fully_configured
from app.services.plant_stop_service import (
    CIRCUIT_AGUA,
    CIRCUIT_FILTRO,
    CIRCUIT_REACTOR,
    CIRCUIT_SALMUERA_E2,
    CIRCUIT_SALMUERA_E3,
)
from app.services.salmuera_analisis_8hs_service import ANALISIS_8HS_INTERVAL_SECONDS
from app.utils.datetime_operacion import now_operacion_naive_local
from app.utils.fechas import fecha_ar

DOMINIO_ENVIO = "informe_analisis"
# Quiénes lo reciben (usuarios del sistema; el mail sale del usuario o de su legajo).
DESTINATARIOS_DEFAULT = ("admin", "silvano", "fernando")
TURNOS: tuple[tuple[str, str, int, int], ...] = (("M", "Mañana", 8, 16), ("T", "Tarde", 16, 24), ("N", "Noche", 24, 32))

_CIRCUITO_E = {2: CIRCUIT_SALMUERA_E2, 3: CIRCUIT_SALMUERA_E3}


def _analisis() -> list[dict[str, Any]]:
    """Tipos de análisis por turno: clave, nombre, circuito de parada, intervalo y filas (momento, operador)."""
    out = []
    for e in SALMUERA_PANEL_ELECTROLIZADORES:
        out.append({"clave": f"salmuera_e{e}", "nombre": f"Hipoclorito · Electrolizador {e}", "circuito": _CIRCUITO_E[e],
                    "intervalo": ANALYSIS_INTERVAL_SECONDS, "modelo": SalmueraRegistro,
                    "filtro": SalmueraRegistro.electrolizador == e})
    out += [
        {"clave": "reactor", "nombre": "Reactor", "circuito": CIRCUIT_REACTOR, "intervalo": ANALYSIS_INTERVAL_SECONDS,
         "modelo": ReactorRegistro},
        {"clave": "agua", "nombre": "Agua", "circuito": CIRCUIT_AGUA, "intervalo": AGUA_ANALYSIS_INTERVAL_SECONDS,
         "modelo": AguaRegistro},
        {"clave": "analisis_8hs", "nombre": "Análisis de 8 hs", "circuito": CIRCUIT_REACTOR,
         "intervalo": ANALISIS_8HS_INTERVAL_SECONDS, "modelo": SalmueraAnalisis8hs},
    ]
    return out


def _momento(row: Any) -> datetime | None:
    raw = getattr(row, "fecha_hora_iso", None) or f"{row.fecha_iso}T{row.hora_hm}"
    try:
        return datetime.fromisoformat(str(raw)[:19])
    except ValueError:
        return None


def _filas(modelo: Any, desde: datetime, hasta: datetime, filtro: Any = None) -> list[Any]:
    fecha_col = modelo.fecha if modelo is SalmueraAnalisis8hs else modelo.fecha_iso
    q = select(modelo).where(fecha_col >= desde.date().isoformat(), fecha_col <= hasta.date().isoformat())
    if filtro is not None:
        q = q.where(filtro)
    rows = [r for r in db.session.scalars(q) if (m := _momento(r)) is not None and desde <= m < hasta]
    return sorted(rows, key=_momento)


def _segundos_parada(circuito: str, desde: datetime, hasta: datetime) -> int:
    total = 0
    for ev in db.session.scalars(select(PlantStopEvent).where(
        PlantStopEvent.circuit_key == circuito, PlantStopEvent.started_at_iso < hasta.isoformat(),
        (PlantStopEvent.ended_at_iso.is_(None)) | (PlantStopEvent.ended_at_iso > desde.isoformat()),
    )):
        ini = max(desde, datetime.fromisoformat(ev.started_at_iso[:19]))
        fin = min(hasta, datetime.fromisoformat(ev.ended_at_iso[:19]) if ev.ended_at_iso else hasta)
        total += max(0, int((fin - ini).total_seconds()))
    return total


def esperados(intervalo: int, segundos_operando: int) -> int:
    """Análisis que entran en el tiempo con planta en marcha (al menos uno si el circuito trabajó una hora)."""
    if segundos_operando < 3600:
        return 0
    return max(1, segundos_operando // int(intervalo))


class _Nombres:
    """Lleva los distintos textos de operador (usuario, «Apellido, Nombre (cargó X)») al nombre completo."""

    def __init__(self) -> None:
        self.por_usuario = {u.username.lower(): (u.nombre_completo or u.username).strip()
                            for u in db.session.scalars(select(User))}

    def de(self, operador: str | None) -> tuple[str, str]:
        raw = (operador or "").strip()
        cargo = re.search(r"\(cargó\s+(.+?)\)\s*$", raw)
        base = re.sub(r"\s*\(.*\)\s*$", "", raw).strip()
        return self.por_usuario.get(base.lower(), base) or "Sin operador", cargo.group(1).strip() if cargo else ""


def _personas_turno(desde: datetime, hasta: datetime) -> list[dict[str, Any]]:
    """Turnos abiertos en el sistema que se superponen con la ventana, con su horario real."""
    out = []
    for s in db.session.scalars(select(ShiftSession).where(
        ShiftSession.started_at_iso < hasta.isoformat(),
        (ShiftSession.ended_at_iso.is_(None)) | (ShiftSession.ended_at_iso > desde.isoformat()),
    ).order_by(ShiftSession.started_at_iso)):
        ini = datetime.fromisoformat(s.started_at_iso[:19])
        fin = datetime.fromisoformat(s.ended_at_iso[:19]) if s.ended_at_iso else None
        solapa = (min(hasta, fin or hasta) - max(desde, ini)).total_seconds()
        u = s.user
        out.append({"nombre": (u.nombre_completo or u.username).strip() if u else "—", "inicio": ini, "fin": fin,
                    "minutos": int(solapa // 60)})
    # Quien cerró o abrió apenas pasado el cambio de turno no es del turno, salvo que no haya otro.
    largos = [p for p in out if p["minutos"] >= 30]
    return largos or out


def armar(dia: date) -> dict[str, Any]:
    """Datos del informe del día operativo ``dia`` (turnos M y T de ese día y N de la madrugada siguiente)."""
    nombres = _Nombres()
    base = datetime.combine(dia, datetime.min.time())
    tipos = _analisis()
    turnos = []
    por_persona: dict[str, dict[str, int]] = defaultdict(lambda: {"hechos": 0, "esperados": 0})
    for codigo, etiqueta, h0, h1 in TURNOS:
        desde, hasta = base + timedelta(hours=h0), base + timedelta(hours=h1)
        personas = _personas_turno(desde, hasta)
        responsable = max(personas, key=lambda p: p["minutos"])["nombre"] if personas else ""
        filas, faltan = [], 0
        for t in tipos:
            rows = _filas(t["modelo"], desde, hasta, t.get("filtro"))
            operando = int((hasta - desde).total_seconds()) - _segundos_parada(t["circuito"], desde, hasta)
            esp = esperados(t["intervalo"], operando)
            quien: dict[str, int] = defaultdict(int)
            cargas = set()
            for r in rows:
                n, cargo = nombres.de(r.operador)
                quien[n] += 1
                if cargo:
                    cargas.add(cargo)
            hechos = len(rows)
            falta = max(0, esp - hechos)
            faltan += falta
            filas.append({"nombre": t["nombre"], "esperados": esp, "hechos": hechos, "faltan": falta,
                          "horas": [_momento(r).strftime("%H:%M") for r in rows], "quien": dict(quien),
                          "cargo": sorted(cargas), "parada": operando < int((hasta - desde).total_seconds())})
            for n, k in quien.items():
                por_persona[n]["hechos"] += k
            if responsable:
                por_persona[responsable]["esperados"] += esp
        turnos.append({"codigo": codigo, "etiqueta": etiqueta, "desde": desde, "hasta": hasta, "personas": personas,
                       "responsable": responsable, "filas": filas, "faltan": faltan,
                       "esperados": sum(f["esperados"] for f in filas), "hechos": sum(f["hechos"] for f in filas)})
    # El lavado de filtro es uno por día, no por turno.
    d0, d1 = base + timedelta(hours=8), base + timedelta(hours=32)
    filtro_rows = _filas(FiltroLavadoRegistro, d0, d1)
    filtro_esp = esperados(FILTRO_LAVADO_INTERVAL_SECONDS,
                           int((d1 - d0).total_seconds()) - _segundos_parada(CIRCUIT_FILTRO, d0, d1))
    filtro = {"esperados": filtro_esp, "hechos": len(filtro_rows),
              "detalle": [f"{_momento(r).strftime('%d/%m %H:%M')} · {nombres.de(r.operador)[0]}" for r in filtro_rows]}
    personas = sorted(({"nombre": n, **v} for n, v in por_persona.items()), key=lambda p: p["nombre"].lower())
    for p in personas:
        p["faltan"] = max(0, p["esperados"] - p["hechos"])
        p["cumplimiento"] = round(100 * min(p["hechos"], p["esperados"]) / p["esperados"]) if p["esperados"] else None
    from app.services.datos_sospechosos_service import analizar

    sospechosos = analizar(d0, d1, [(t["desde"], t["hasta"]) for t in turnos])
    return {"dia": dia, "turnos": turnos, "filtro": filtro, "personas": personas, "sospechosos": sospechosos,
            "faltan": sum(t["faltan"] for t in turnos) + max(0, filtro_esp - len(filtro_rows))}


def destinatarios(app: Any) -> list[str]:
    usuarios = [u.strip().lower() for u in str(app.config.get("INFORME_ANALISIS_USUARIOS") or "").split(",") if u.strip()]
    out = []
    for u in db.session.scalars(select(User).where(
        func.lower(User.username).in_(usuarios or list(DESTINATARIOS_DEFAULT)), User.activo.is_(True)
    )):
        mail = normalize_validate_email(u.email or "")
        if not mail:
            emp = db.session.scalar(select(EmpleadoPersonal).where(EmpleadoPersonal.user_id == u.id))
            mail = normalize_validate_email((emp.email or "") if emp else "")
        if mail and mail not in out:
            out.append(mail)
    return out


def _h(x: Any) -> str:
    return html.escape(str(x))


def _semaforo(hechos: int, esperados: int) -> str:
    if esperados == 0:
        return "#6c757d"
    return "#198754" if hechos >= esperados else ("#dc3545" if hechos == 0 else "#fd7e14")


def cuerpos(data: dict[str, Any]) -> tuple[str, str, str]:
    """Asunto, HTML y texto (el texto también va por WhatsApp)."""
    dia = fecha_ar(data["dia"].isoformat())
    asunto = (f"Análisis por turno del {dia}: " +
              (f"faltaron {data['faltan']}" if data["faltan"] else "se hicieron todos"))
    sos = data.get("sospechosos") or {"indicios": [], "personas": [], "aprendido": [], "resumen": {}}
    alertas = [p for p in sos["personas"] if p["alerta"]]
    if sos["indicios"] or alertas:
        asunto += f" · {len(sos['indicios'])} posible(s) dato(s) falso(s)"
    td = 'style="border:1px solid #ccc;padding:4px 8px"'
    partes = [f"<h2 style='margin:0 0 4px'>Análisis por turno · {dia}</h2>",
              "<p style='margin:0 0 12px;color:#555'>Turnos M y T del día y N de la madrugada siguiente. "
              "Esperados según la frecuencia de cada análisis, descontando paradas de planta declaradas.</p>",
              "<h3>Resumen por persona</h3>",
              f"<table style='border-collapse:collapse'><tr><th {td}>Persona</th><th {td}>Esperados</th>"
              f"<th {td}>Hechos</th><th {td}>Faltaron</th><th {td}>Cumplimiento</th></tr>"]
    texto = [f"ANÁLISIS POR TURNO · {dia}", ""]
    for p in data["personas"]:
        cump = f"{p['cumplimiento']} %" if p["cumplimiento"] is not None else "—"
        color = _semaforo(p["hechos"], p["esperados"])
        partes.append(f"<tr><td {td}>{_h(p['nombre'])}</td><td {td}>{p['esperados']}</td><td {td}>{p['hechos']}</td>"
                      f"<td style='border:1px solid #ccc;padding:4px 8px;color:{color};font-weight:bold'>{p['faltan']}</td>"
                      f"<td {td}>{cump}</td></tr>")
        texto.append(f"{p['nombre']}: {p['hechos']} de {p['esperados']} ({cump})" if p["esperados"]
                     else f"{p['nombre']}: {p['hechos']} (no se esperaban: planta parada)")
    partes.append("</table>")
    for t in data["turnos"]:
        horario = f"{t['desde'].strftime('%d/%m %H:%M')} a {t['hasta'].strftime('%H:%M')}"
        if t["personas"]:
            quienes = "; ".join(
                f"{p['nombre']} (abrió {p['inicio'].strftime('%H:%M')}, "
                f"{'cerró ' + p['fin'].strftime('%H:%M') if p['fin'] else 'sin cerrar'})" for p in t["personas"])
        else:
            quienes = "nadie abrió turno en el sistema"
        partes.append(f"<h3 style='margin-top:18px'>Turno {t['etiqueta']} · {horario}</h3><p style='margin:0 0 6px'>{_h(quienes)}</p>"
                      f"<table style='border-collapse:collapse'><tr><th {td}>Análisis</th><th {td}>Esperados</th>"
                      f"<th {td}>Hechos</th><th {td}>Horarios</th><th {td}>Quién</th></tr>")
        texto += ["", f"Turno {t['etiqueta']} ({horario}): {t['hechos']} de {t['esperados']} — {quienes}"]
        for f in t["filas"]:
            color = _semaforo(f["hechos"], f["esperados"])
            quien = ", ".join(f"{n} ({k})" for n, k in f["quien"].items()) or "—"
            if f["cargo"]:
                quien += f" · cargó {', '.join(f['cargo'])}"
            nota = " (con parada)" if f["parada"] else ""
            partes.append(f"<tr><td {td}>{_h(f['nombre'])}{nota}</td><td {td}>{f['esperados']}</td>"
                          f"<td style='border:1px solid #ccc;padding:4px 8px;color:{color};font-weight:bold'>{f['hechos']}</td>"
                          f"<td {td}>{_h(', '.join(f['horas']) or '—')}</td><td {td}>{_h(quien)}</td></tr>")
            if f["faltan"]:
                texto.append(f"  · {f['nombre']}: {f['hechos']} de {f['esperados']}")
        partes.append("</table>")
    fl = data["filtro"]
    partes.append(f"<h3 style='margin-top:18px'>Lavado de filtro (uno por día)</h3><p>"
                  f"{fl['hechos']} de {fl['esperados']}: {_h('; '.join(fl['detalle']) or 'no se registró')}</p>")
    texto += ["", f"Lavado de filtro: {fl['hechos']} de {fl['esperados']}"]
    _seccion_sospechosos(sos, alertas, partes, texto, td)
    return asunto, "".join(partes), "\n".join(texto)


def _seccion_sospechosos(sos: dict[str, Any], alertas: list[dict[str, Any]], partes: list[str], texto: list[str], td: str) -> None:
    partes.append("<h3 style='margin-top:22px'>Posibles datos falsos</h3><p style='margin:0 0 6px;color:#555'>"
                  "El sistema aprende de los últimos 60 días cómo varían los valores y cuáles se mueven juntos, y marca "
                  "lo que no encaja. Son indicios para revisar con el personal, no pruebas.</p>")
    texto += ["", "POSIBLES DATOS FALSOS"]
    if not sos["indicios"] and not alertas:
        partes.append("<p>Sin indicios en el día.</p>")
        texto.append("Sin indicios en el día.")
    if sos["resumen"]:
        partes.append(f"<table style='border-collapse:collapse'><tr><th {td}>Persona</th><th {td}>Copias del anterior</th>"
                      f"<th {td}>Sin variación</th><th {td}>No cierran</th><th {td}>Fuera de lo habitual</th></tr>")
        for p, v in sorted(sos["resumen"].items(), key=lambda kv: -kv[1].get("_puntos", 0)):
            partes.append(f"<tr><td {td}>{_h(p)}</td>" + "".join(
                f"<td {td}>{v.get(k, 0)}</td>" for k in ("Copia del anterior", "Sin variación en el turno", "No cierra",
                                                        "Fuera de lo habitual")) + "</tr>")
        partes.append("</table><ul style='margin-top:8px'>")
        for i in sos["indicios"]:
            linea = f"{i['momento'].strftime('%d/%m %H:%M')} · {i['persona']} · {i['analisis']} · {i['tipo']}: {i['texto']}"
            color = "#dc3545" if i["peso"] >= 2 else "#555"
            partes.append(f"<li style='color:{color}'>{_h(linea)}</li>")
            texto.append(f"· {linea}")
        partes.append("</ul>")
    if alertas:
        partes.append("<p style='margin:10px 0 4px'><b>Repiten valores mucho más que el resto (últimos 30 días)</b></p><ul>")
        for p in alertas:
            resto = f"{round(100 * p['resto'])} %" if p["resto"] is not None else "—"
            linea = (f"{p['persona']} · {p['analisis']}: {p['copias']} de {p['n']} análisis iguales al anterior "
                     f"({round(100 * p['tasa'])} %); el resto del equipo, {resto}")
            partes.append(f"<li style='color:#dc3545'>{_h(linea)}</li>")
            texto.append(f"· {linea}")
        partes.append("</ul>")
    if sos["aprendido"]:
        rel = "; ".join(f"{a['analisis']}: {a['y']} con {a['x']} (r = {a['r']:.2f})".replace(".", ",") for a in sos["aprendido"])
        partes.append(f"<p style='color:#777;font-size:12px;margin-top:10px'>Relaciones aprendidas: {_h(rel)}.</p>")


def ayer() -> date:
    return now_operacion_naive_local().date() - timedelta(days=1)


def run_informe_analisis(app: Any, *, dia: date | None = None, dry_run: bool = False, forzar: bool = False) -> dict[str, Any]:
    dia = dia or ayer()
    clave = int(dia.strftime("%Y%m%d"))
    data = armar(dia)
    asunto, cuerpo_html, cuerpo_texto = cuerpos(data)
    para = destinatarios(app)
    out: dict[str, Any] = {"dia": dia.isoformat(), "faltan": data["faltan"], "destinatarios": len(para),
                           "enviado": False, "asunto": asunto, "texto": cuerpo_texto}
    ya = db.session.scalar(select(DeadlineReminderSent).where(
        DeadlineReminderSent.domain == DOMINIO_ENVIO, DeadlineReminderSent.entity_id == clave))
    if dry_run:
        out["message"] = "Simulación: no se envió."
        return out
    if ya is not None and not forzar:
        out["message"] = "El informe de ese día ya se había enviado."
        return out
    if not para or not is_mail_fully_configured(app):
        out["message"] = "Sin destinatarios con mail o SMTP sin configurar."
        return out
    enviar_mail(app, destinatarios=para, asunto=asunto, cuerpo_html=cuerpo_html, cuerpo_texto=cuerpo_texto)
    if ya is None:
        db.session.add(DeadlineReminderSent(domain=DOMINIO_ENVIO, entity_id=clave))
    db.session.commit()
    out["enviado"] = True
    out["message"] = f"Informe de análisis enviado a {len(para)} destinatario(s)."
    return out
