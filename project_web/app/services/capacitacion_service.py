"""Registro de capacitación (registro SGI QDV-RG-PG-05_03): una hoja por capacitación, editable, con historial.

Cada asistente con usuario del sistema (legajo vinculado) firma su renglón desde el sistema o desde el aviso (mail con
link o WhatsApp), igual que la minuta de reunión. El disertante firma desde el link que le llega a su correo (o desde el
sistema si tiene usuario). Si se modifican los datos de la capacitación o la lista de asistentes, las firmas se anulan;
las conclusiones de eficacia se completan después y no las anulan.
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import Capacitacion, CapacitacionCambio, EmpleadoPersonal, User
from app.services.fichas_proceso_service import fecha_local
from app.services.plan_accion_service import fecha_dmy, parse_fecha

log = logging.getLogger(__name__)

REGISTRO = {
    "codigo": "QDV-RG-PG-05_03",
    "titulo": "REGISTRO DE CAPACITACIÓN",
    "fecha_vigencia": date(2026, 11, 24),
    "revision": "01",
}
CONTROL_CAMBIOS: tuple[tuple[str, str, str], ...] = (
    ("00", "Confección del registro", "02/06/2026"),
    ("01", "Firma de los asistentes y del disertante en el sistema", "24/11/2026"),
)
FIRMA_CAMPOS: tuple[str, ...] = ("firma_at", "firma_via")
# Si cambia alguno de estos campos, lo firmado ya no es lo mismo: las firmas se anulan.
CAMPOS_FIRMADOS: tuple[str, ...] = ("fecha", "lugar", "duracion", "disertantes", "tema", "material", "asistentes")
# Métodos de evaluación de la eficacia, en el orden de la planilla.
METODOS: tuple[tuple[str, str], ...] = (
    ("escrita", "Evaluación escrita"),
    ("oral", "Evaluación oral"),
    ("desempeno", "Evaluación de desempeño"),
    ("auditorias", "Resultado de auditorías Internas/externas"),
    ("cliente", "Satisfacción del Cliente"),
    ("otros", "Otros"),
)
SI_NO: tuple[str, ...] = ("SI", "NO")
FILAS_ASISTENTES = 17  # renglones de la planilla Word
CAMPOS_TEXTO: tuple[str, ...] = ("lugar", "duracion", "disertantes", "tema", "material", "nuevas_acciones_detalle")
_LARGOS = {"lugar": 255, "duracion": 60, "disertantes": 255}
CAMPO_LABELS: dict[str, str] = {
    "numero": "N° capacitación",
    "fecha": "Fecha",
    "lugar": "Lugar",
    "duracion": "Duración",
    "disertantes": "Disertante/es",
    "tema": "Tema",
    "material": "Material que se entrega",
    "metodos": "Método de evaluación de la eficacia",
    "asistentes": "Asistentes",
    "eficaz": "¿Fue eficaz la capacitación realizada?",
    "nuevas_acciones": "¿Se deben realizar nuevas acciones?",
    "nuevas_acciones_detalle": "Nuevas acciones",
    "disertante_correo": "Correo del disertante",
    "alta": "Alta",
    "baja": "Baja",
    "firma": "Firma",
    "firmas": "Firmas",
}


def metodos(c: Capacitacion | None) -> dict[str, dict[str, Any]]:
    if c is None:
        return {}
    try:
        data = json.loads(c.metodos or "{}")
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def asistentes(c: Capacitacion | None) -> list[dict[str, Any]]:
    if c is None:
        return []
    try:
        data = json.loads(c.asistentes or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def empleados() -> list[EmpleadoPersonal]:
    return list(
        db.session.scalars(
            select(EmpleadoPersonal)
            .where(EmpleadoPersonal.estado == "activo")
            .order_by(EmpleadoPersonal.apellido, EmpleadoPersonal.nombre)
        )
    )


def labels_context() -> dict[str, Any]:
    return {
        "reg": REGISTRO, "metodos_op": METODOS, "si_no": SI_NO, "cp_campo_labels": CAMPO_LABELS, "fecha_local": fecha_local,
        "fecha_dmy": fecha_dmy, "metodos": metodos, "asistentes": asistentes, "filas_asistentes": FILAS_ASISTENTES,
        "firma_texto": firma_texto, "disertante": disertante, "firma_disertante_texto": firma_disertante_texto,
        "control_cambios": CONTROL_CAMBIOS, "firmas": firmas,
    }


def listar() -> list[Capacitacion]:
    return list(
        db.session.scalars(
            select(Capacitacion).where(Capacitacion.activo.is_(True)).order_by(Capacitacion.numero.desc())
        )
    )


def get(capacitacion_id: int) -> Capacitacion | None:
    c = db.session.get(Capacitacion, int(capacitacion_id))
    return c if c is not None and c.activo else None


def cambios(c: Capacitacion, limit: int = 100) -> list[CapacitacionCambio]:
    return list(
        db.session.scalars(
            select(CapacitacionCambio)
            .where(CapacitacionCambio.capacitacion_id == c.id)
            .order_by(CapacitacionCambio.created_at.desc(), CapacitacionCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(c: Capacitacion, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        CapacitacionCambio(
            capacitacion_id=c.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes in (None, "") else str(antes),
            despues=None if despues in (None, "") else str(despues),
        )
    )


def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode()
    return re.sub(r"[\s,]+", " ", x).strip().lower()


def _legajos() -> dict[str, int]:
    """«apellido nombre» y «nombre apellido» normalizados → id del legajo activo."""
    out: dict[str, int] = {}
    for emp in empleados():
        out.setdefault(_norm(f"{emp.apellido} {emp.nombre}"), emp.id)
        out.setdefault(_norm(f"{emp.nombre} {emp.apellido}"), emp.id)
    return out


def _corto(val: Any, largo: int = 255) -> str:
    return re.sub(r"\s+", " ", str(val or "")).strip()[:largo]


def _metodos(data: Any) -> str:
    if hasattr(data, "getlist"):  # formulario: m_<clave>, m_<clave>_detalle/_responsable/_plazo
        crudos = {
            k: {"marcado": bool(data.get(f"m_{k}")), **{x: data.get(f"m_{k}_{x}") for x in ("detalle", "responsable", "plazo")}}
            for k, _ in METODOS
        }
    else:
        crudos = data.get("metodos") or {}
    out: dict[str, dict[str, Any]] = {}
    for k, _ in METODOS:
        cr = crudos.get(k) or {}
        fila = {"marcado": bool(cr.get("marcado")), **{x: _corto(cr.get(x)) for x in ("detalle", "responsable", "plazo")}}
        if fila["marcado"] or any(fila[x] for x in ("detalle", "responsable", "plazo")):
            out[k] = fila
    return json.dumps(out, ensure_ascii=False)


def _asistentes(data: Any) -> str:
    if hasattr(data, "getlist"):  # formulario: as_nombre_<i>, as_sector_<i>
        crudas = [
            {"nombre": data.get(f"as_nombre_{i}"), "sector": data.get(f"as_sector_{i}")}
            for i in range(int(data.get("as_filas") or 0))
        ]
    else:
        crudas = list(data.get("asistentes") or [])
    legajos = _legajos()
    out: list[dict[str, Any]] = []
    for cruda in crudas:
        fila: dict[str, Any] = {"nombre": _corto(cruda.get("nombre")), "sector": _corto(cruda.get("sector"))}
        if not fila["nombre"] and not fila["sector"]:
            continue
        emp_id = legajos.get(_norm(fila["nombre"]))
        if emp_id:
            fila["empleado_id"] = emp_id
            emp = db.session.get(EmpleadoPersonal, emp_id)
            if emp is not None and emp.user_id:
                fila["user_id"] = int(emp.user_id)
        out.append(fila)
    return json.dumps(out, ensure_ascii=False)


def _limpio(data: Any) -> tuple[dict[str, Any], list[str]]:
    v: dict[str, Any] = {}
    errores: list[str] = []
    for k in CAMPOS_TEXTO:
        val = str(data.get(k) or "").strip()
        v[k] = _corto(val, _LARGOS[k]) if k in _LARGOS else val
    try:
        v["fecha"] = parse_fecha(data.get("fecha"))
    except ValueError:
        errores.append("Fecha: fecha inválida, usá dd/mm/aaaa.")
        v["fecha"] = None
    for k in ("eficaz", "nuevas_acciones"):
        val = _norm(str(data.get(k) or "")).upper()
        v[k] = val if val in SI_NO else ""
    v["metodos"] = _metodos(data)
    v["asistentes"] = _asistentes(data)
    correo = _corto(data.get("disertante_correo"), 254).lower()
    if correo and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        errores.append("Correo del disertante: no es un correo válido.")
    v["disertante_correo"] = correo
    if not v["tema"]:
        errores.append("El tema es obligatorio.")
    return v, errores


def _fmt(campo: str, val: Any) -> Any:
    if not val:
        return val
    if campo == "fecha":
        return fecha_dmy(val)
    if campo == "metodos":
        nombres = dict(METODOS)
        return "\n".join(
            " · ".join(x for x in (("☒ " if m["marcado"] else "☐ ") + nombres.get(k, k), m.get("detalle"), m.get("responsable"), m.get("plazo")) if x)
            for k, m in json.loads(val).items()
        ) or None
    if campo == "asistentes":
        return "\n".join(f"{a.get('nombre') or '—'} · {a.get('sector') or '—'}" for a in json.loads(val)) or None
    return val


def _sin_firmas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in f.items() if k not in FIRMA_CAMPOS} for f in rows]


def _disertante_nuevo(c: Capacitacion | None, disertantes: str, correo: str) -> dict[str, Any]:
    """Firma del disertante: su usuario si el nombre coincide con uno solo, y el correo al que se le pide la firma."""
    from app.services.minuta_reunion_service import usuario_de

    d: dict[str, Any] = {}
    u = usuario_de(disertantes) if disertantes else None
    if u is not None:
        d["user_id"] = int(u.id)
    if correo:
        d["correo"] = correo
    elif u is not None:
        from app.services.sgi_difusion_mail_service import _user_emails

        mails = _user_emails(u)
        if mails:
            d["correo"] = mails[0].lower()
    prev = disertante(c)
    if prev.get("firma_at") and (prev.get("correo"), prev.get("user_id")) == (d.get("correo"), d.get("user_id")):
        d.update({k: prev[k] for k in FIRMA_CAMPOS if prev.get(k)})
    return d


def guardar(c: Capacitacion, data: Any, user_id: int | None) -> list[str]:
    v, errores = _limpio(data)
    if errores:
        return errores
    correo = v.pop("disertante_correo")
    anteriores = asistentes(c)
    nuevos = json.loads(v["asistentes"])
    por_emp = {f["empleado_id"]: f for f in anteriores if f.get("empleado_id") and f.get("firma_at")}
    for f in nuevos:  # conservar la firma de quien sigue (se anula abajo si cambió algo firmado)
        prev = por_emp.get(f.get("empleado_id"))
        if prev is not None and prev.get("user_id") == f.get("user_id"):
            f.update({k: prev[k] for k in FIRMA_CAMPOS if prev.get(k)})
    v["asistentes"] = json.dumps(nuevos, ensure_ascii=False)
    firmado_cambio = False
    for campo, nuevo in v.items():
        antes = getattr(c, campo)
        if campo == "asistentes":
            if _sin_firmas(json.loads(antes or "[]")) == _sin_firmas(json.loads(nuevo)):
                continue
        elif campo == "metodos" and json.loads(antes or "null") == json.loads(nuevo):
            continue
        elif (antes or None) == (nuevo or None):
            continue
        setattr(c, campo, nuevo)
        firmado_cambio = firmado_cambio or campo in CAMPOS_FIRMADOS
        _log(c, user_id, campo, _fmt(campo, antes), _fmt(campo, nuevo))
    dis_antes = disertante(c)
    dis = _disertante_nuevo(c, c.disertantes, correo)
    if dis.get("correo") != dis_antes.get("correo"):
        _log(c, user_id, "disertante_correo", dis_antes.get("correo"), dis.get("correo"))
    firmadas = [f["nombre"] for f in anteriores if f.get("firma_at")] + (["el disertante"] if dis_antes.get("firma_at") else [])
    if firmado_cambio and firmadas:
        c.asistentes = json.dumps(_sin_firmas(asistentes(c)), ensure_ascii=False)
        dis = {k: v for k, v in dis.items() if k not in FIRMA_CAMPOS}
        _log(c, user_id, "firmas", "Firmada por: " + ", ".join(firmadas),
             "Anuladas porque se modificó la capacitación: tienen que volver a firmar.")
    c.disertante_firma = json.dumps(dis, ensure_ascii=False)
    return []


def crear(data: Any, user_id: int | None) -> tuple[Capacitacion | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    correo = v.pop("disertante_correo")
    numero = (db.session.scalar(select(func.max(Capacitacion.numero))) or 0) + 1
    c = Capacitacion(numero=numero, **v)
    c.disertante_firma = json.dumps(_disertante_nuevo(None, c.disertantes, correo), ensure_ascii=False)
    db.session.add(c)
    db.session.flush()
    _log(c, user_id, "alta", None, f"N° {numero}: {c.tema}")
    return c, []


def baja(c: Capacitacion, user_id: int | None) -> None:
    c.activo = False
    _log(c, user_id, "baja", f"N° {c.numero}: {c.tema}", None)


# ------------------------------------------------------------------ firmas


def disertante(c: Capacitacion | None) -> dict[str, Any]:
    if c is None:
        return {}
    try:
        data = json.loads(c.disertante_firma or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _firmado(fila: dict[str, Any]) -> str:
    cuando = fecha_local(datetime.fromisoformat(fila["firma_at"]))
    return f"Firmado en el sistema ({fila.get('firma_via') or 'sistema'}) · {cuando}"


def firma_texto(fila: dict[str, Any]) -> str:
    """Columna FIRMA de un asistente: la firma en el sistema reemplaza a la firma en papel."""
    if fila.get("firma_at"):
        return _firmado(fila)
    if not fila.get("user_id"):
        return "Sin usuario del sistema"
    return "Pendiente de firma"


def firma_disertante_texto(c: Capacitacion) -> str:
    d = disertante(c)
    if d.get("firma_at"):
        return _firmado(d)
    if d.get("correo") or d.get("user_id"):
        return "Pendiente de firma"
    return "Falta el correo del disertante para pedirle la firma"


def _asistentes_pendientes(c: Capacitacion) -> list[tuple[dict[str, Any], User]]:
    out = []
    for f in asistentes(c):
        if f.get("user_id") and not f.get("firma_at"):
            u = db.session.get(User, int(f["user_id"]))
            if u is not None and u.activo:
                out.append((f, u))
    return out


def _disertante_pendiente(c: Capacitacion) -> bool:
    d = disertante(c)
    return bool(d.get("correo") or d.get("user_id")) and not d.get("firma_at")


def firmas(c: Capacitacion | None) -> tuple[int, int]:
    """(firmadas, a firmar): asistentes con usuario y el disertante si tiene correo o usuario."""
    if c is None:
        return 0, 0
    a = [f for f in asistentes(c) if f.get("user_id") or f.get("firma_at")]
    d = disertante(c)
    total = len(a) + (1 if d.get("correo") or d.get("user_id") or d.get("firma_at") else 0)
    return sum(1 for f in a if f.get("firma_at")) + (1 if d.get("firma_at") else 0), total


def es_disertante(c: Capacitacion, user: User | None) -> bool:
    d = disertante(c)
    return user is not None and bool(d.get("user_id")) and int(d["user_id"]) == int(user.id)


def puede_firmar(c: Capacitacion, user: User | None) -> bool:
    if user is None or not c.activo:
        return False
    if any(int(u.id) == int(user.id) for _, u in _asistentes_pendientes(c)):
        return True
    return es_disertante(c, user) and _disertante_pendiente(c)


def _audit(c: Capacitacion, user: User | None, detalle: str, email: str = "") -> None:
    from app.services import security_audit_service as audit_svc

    audit_svc.record_event(action="capacitacion_firmada", module="sgi", actor=user,
                           actor_username=None if user is not None else (email or None), entity_type="capacitacion",
                           entity_id=c.id, detail=f"Capacitación N° {c.numero}: {detalle}")


def firmar(c: Capacitacion, user: User, via: str = "sistema") -> str:
    """Firma lo que le toque a ese usuario: su renglón de asistente y, si es el disertante, la firma del disertante."""
    if not c.activo:
        raise ValueError("La capacitación fue dada de baja.")
    rows = asistentes(c)
    hechas = []
    for f in rows:
        if f.get("user_id") == int(user.id) and not f.get("firma_at"):
            f["firma_at"], f["firma_via"] = _ahora_iso(), via
            hechas.append(f"asistente {f['nombre']}")
    c.asistentes = json.dumps(rows, ensure_ascii=False)
    if es_disertante(c, user) and _disertante_pendiente(c):
        d = disertante(c)
        d["firma_at"], d["firma_via"] = _ahora_iso(), via
        c.disertante_firma = json.dumps(d, ensure_ascii=False)
        hechas.append(f"disertante {c.disertantes}")
    if not hechas:
        raise ValueError("No tenés esta capacitación pendiente de firma.")
    for h in hechas:
        _log(c, int(user.id), "firma", None, f"Firmó {h} ({via})")
    _audit(c, user, ", ".join(hechas) + f" ({via})")
    return f"Listo, firmaste el Registro de capacitación N° {c.numero}."


def firmar_disertante(c: Capacitacion, email: str, via: str = "link del aviso", user: User | None = None) -> str:
    """Firma del disertante desde el link que llegó a su correo (puede no tener usuario del sistema)."""
    if not c.activo:
        raise ValueError("La capacitación fue dada de baja.")
    d = disertante(c)
    if d.get("firma_at"):
        raise ValueError("El disertante ya firmó esta capacitación.")
    if not d.get("correo") or (email or "").strip().lower() != d["correo"]:
        raise ValueError("Este link ya no corresponde: el correo del disertante cambió.")
    d["firma_at"], d["firma_via"] = _ahora_iso(), via
    c.disertante_firma = json.dumps(d, ensure_ascii=False)
    _log(c, int(user.id) if user is not None else None, "firma", None, f"Firmó el disertante {c.disertantes} ({via}, {d['correo']})")
    _audit(c, user, f"disertante {c.disertantes} ({via})", email=d["correo"])
    return f"Listo, quedó firmado como disertante el Registro de capacitación N° {c.numero}."


def disertante_puede_firmar_link(c: Capacitacion, email: str) -> bool:
    d = disertante(c)
    return c.activo and _disertante_pendiente(c) and bool(d.get("correo")) and (email or "").strip().lower() == d["correo"]


def texto_capacitacion(c: Capacitacion) -> str:
    """La capacitación en texto, para leerla en el aviso antes de firmar."""
    asis = "\n".join(f"- {a.get('nombre')} ({a.get('sector') or 'sin sector'})" for a in asistentes(c))
    return (
        f"Registro de capacitación N° {c.numero} ({REGISTRO['codigo']})\n"
        f"Fecha: {fecha_dmy(c.fecha) if c.fecha else ''} · Lugar: {c.lugar} · Duración: {c.duracion}\n"
        f"Disertante/es: {c.disertantes}\nTema: {c.tema}\nMaterial que se entrega: {c.material}\n\nAsistentes:\n{asis}"
    )


def avisar_firmas(app: Any, c: Capacitacion, excluir_user_id: int | None = None) -> int:
    """Pide la firma a cada asistente que falta y al disertante (mail con link y copia por WhatsApp). Devuelve a cuántos."""
    from app.services import accion_link_service as accion_svc
    from app.services.mail_service import enviar_mail, is_mail_fully_configured
    from app.services.sgi_difusion_mail_service import _user_emails

    if not is_mail_fully_configured(app):
        log.warning("Capacitación %s: SMTP no configurado, no se piden firmas", c.id)
        return 0
    texto = texto_capacitacion(c)
    fecha = fecha_dmy(c.fecha) if c.fecha else ""
    destinos: list[tuple[str, int | None, str, str]] = []  # (mail, user_id, rol, saludo)
    for _, u in _asistentes_pendientes(c):
        if excluir_user_id is not None and int(u.id) == int(excluir_user_id):
            continue
        mails = _user_emails(u)
        if mails:
            destinos.append((mails[0], int(u.id), "a", "Asististe a la capacitación"))
    d = disertante(c)
    if _disertante_pendiente(c) and d.get("correo") and not (excluir_user_id and d.get("user_id") == excluir_user_id):
        if not any(m.lower() == d["correo"] for m, *_ in destinos):
            destinos.append((d["correo"], d.get("user_id"), "d", "Diste la capacitación"))
    avisados = 0
    for mail, uid, rol, saludo in destinos:
        extra = {"r": "d"} if rol == "d" else {}
        link = accion_svc.url(app, accion_svc.CAP_FIRMAR, c.id, email=mail, user_id=uid, **extra)
        que = "como disertante" if rol == "d" else "tu asistencia"
        try:
            enviar_mail(
                app,
                destinatarios=[mail],
                asunto=f"QDV SGI — Firmar el Registro de capacitación N° {c.numero}",
                cuerpo_html=(
                    f"<p>{saludo} del {html_lib.escape(fecha)} y te toca <strong>firmar el registro {que}</strong>. Leelo:</p>"
                    f'<pre style="white-space:pre-wrap;font-family:inherit">{html_lib.escape(texto)}</pre>'
                    f'<p><a href="{html_lib.escape(link)}"><strong>Firmar el registro</strong></a> '
                    "(desde el celular, sin entrar al sistema)</p>"
                ),
                cuerpo_texto=f"{saludo} del {fecha} y te toca firmar el registro {que}. Leelo:\n\n{texto}\n\nFirmar: {link}",
                texto_whatsapp=(
                    f"{saludo} del {fecha}: te toca firmar el Registro de capacitación N° {c.numero} {que}. "
                    f"Leelo:\n\n{texto}\n\nSi está bien, respondeme *FIRMAR*. Si hay algo para corregir, avisale a quien lo cargó."
                ),
            )
            avisados += 1
        except Exception:
            log.exception("Capacitación %s: falló el aviso de firma a %s", c.id, mail)
    return avisados
