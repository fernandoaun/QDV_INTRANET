"""Minuta de reunión (registro SGI QDV-RG-PG-04_01): una hoja por reunión, editable, con historial.

Todos los campos son obligatorios. Cada participante presente con usuario del sistema la firma desde el
sistema o desde el aviso (mail con link o WhatsApp), como la confirmación de entregas de EPP: la firma
queda en el renglón del participante con fecha y hora. Si la minuta se modifica, las firmas se anulan.
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
from app.models import MinutaReunion, MinutaReunionCambio, User
from app.services import plan_accion_service as plan
from app.services.fichas_proceso_service import fecha_local
from app.services.plan_accion_service import fecha_dmy, parse_fecha

log = logging.getLogger(__name__)

REGISTRO = {
    "codigo": "QDV-RG-PG-04_01",
    "titulo": "MINUTA DE REUNIÓN",
    "fecha_vigencia": date(2026, 11, 6),
    "revision": "01",
}
# Control de cambios del registro (pie de la hoja).
CONTROL_CAMBIOS: tuple[tuple[str, str, str], ...] = (
    ("00", "Confección del documento", "08/09/2026"),
    ("01", "Firma de los participantes en el sistema; todos los campos obligatorios", "06/11/2026"),
)
ASISTENCIA: tuple[str, ...] = ("Presente", "Ausente")
# Tablas de la hoja: campos de cada renglón y renglones del formulario Word.
TABLAS: dict[str, tuple[str, ...]] = {
    "participantes": ("participante", "sector", "asistencia"),
    "acciones": ("accion", "responsable", "fecha"),
}
FILAS: dict[str, int] = {"participantes": 10, "acciones": 3}
CAMPOS_TEXTO: tuple[str, ...] = ("horario", "lugar", "motivo", "desarrollo")
# Lo que agrega el sistema a cada participante: su usuario y su firma.
FIRMA_CAMPOS: tuple[str, ...] = ("firma_at", "firma_via")
_LARGOS = {"horario": 60, "lugar": 255}
CAMPO_LABELS: dict[str, str] = {
    "numero": "N° minuta",
    "fecha": "Fecha",
    "horario": "Horario",
    "lugar": "Lugar",
    "motivo": "Motivo de la reunión",
    "participantes": "Participantes",
    "desarrollo": "Desarrollo",
    "acciones": "Acciones / conclusiones",
    "alta": "Alta",
    "baja": "Baja",
    "firma": "Firma",
    "firmas": "Firmas",
}


def filas(m: MinutaReunion | None, tabla: str) -> list[dict[str, str]]:
    if m is None:
        return []
    try:
        data = json.loads(getattr(m, tabla) or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)]


def presentes(m: MinutaReunion) -> int:
    return sum(1 for p in filas(m, "participantes") if p.get("asistencia") == "Presente")


def labels_context() -> dict[str, Any]:
    return {
        "reg": REGISTRO, "asistencia_op": ASISTENCIA, "mr_campo_labels": CAMPO_LABELS, "fecha_local": fecha_local,
        "fecha_dmy": fecha_dmy, "filas": filas, "filas_min": FILAS, "presentes": presentes, "plan_numeros": plan_numeros,
        "firma_texto": firma_texto, "control_cambios": CONTROL_CAMBIOS,
    }


def listar() -> list[MinutaReunion]:
    return list(
        db.session.scalars(
            select(MinutaReunion).where(MinutaReunion.activo.is_(True)).order_by(MinutaReunion.numero.desc())
        )
    )


def get(minuta_id: int) -> MinutaReunion | None:
    m = db.session.get(MinutaReunion, int(minuta_id))
    return m if m is not None and m.activo else None


def cambios(m: MinutaReunion, limit: int = 100) -> list[MinutaReunionCambio]:
    return list(
        db.session.scalars(
            select(MinutaReunionCambio)
            .where(MinutaReunionCambio.minuta_id == m.id)
            .order_by(MinutaReunionCambio.created_at.desc(), MinutaReunionCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(m: MinutaReunion, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        MinutaReunionCambio(
            minuta_id=m.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes in (None, "") else str(antes),
            despues=None if despues in (None, "") else str(despues),
        )
    )


def _tabla(data: Any, tabla: str, errores: list[str]) -> str:
    """Renglones de la tabla desde el formulario (<tabla>_<campo>_<i>) o desde una lista; descarta los vacíos."""
    campos = TABLAS[tabla]
    if hasattr(data, "getlist"):
        crudas = [
            {**{k: data.get(f"{tabla}_{k}_{i}") for k in campos}, "plan_accion_id": data.get(f"{tabla}_plan_{i}")}
            for i in range(int(data.get(f"{tabla}_filas") or 0))
        ]
    else:
        crudas = list(data.get(tabla) or [])
    out: list[dict[str, str]] = []
    for i, cruda in enumerate(crudas):
        fila = {k: re.sub(r"\s+", " ", str(cruda.get(k) or "")).strip()[:255] for k in campos}
        if not any(fila.values()):
            continue
        if not all(fila.values()):
            errores.append(f"{CAMPO_LABELS[tabla]}, renglón {i + 1}: completá todas las columnas.")
        if fila.get("asistencia"):
            fila["asistencia"] = next((a for a in ASISTENCIA if a.lower() == fila["asistencia"].lower()), fila["asistencia"])
        if fila.get("fecha"):
            try:
                fila["fecha"] = fecha_dmy(parse_fecha(fila["fecha"]))
            except ValueError:
                errores.append(f"{CAMPO_LABELS[tabla]}, renglón {i + 1}: fecha inválida, usá dd/mm/aaaa.")
        if str(cruda.get("plan_accion_id") or "").isdigit():
            fila["plan_accion_id"] = int(cruda["plan_accion_id"])
        out.append(fila)
    return json.dumps(out, ensure_ascii=False)


def _limpio(data: Any) -> tuple[dict[str, Any], list[str]]:
    v: dict[str, Any] = {}
    errores: list[str] = []
    for k in CAMPOS_TEXTO:
        val = str(data.get(k) or "").strip()
        v[k] = re.sub(r"\s+", " ", val)[: _LARGOS[k]] if k in _LARGOS else val
    try:
        v["fecha"] = parse_fecha(data.get("fecha"))
        if v["fecha"] is None:
            errores.append("Fecha: es obligatoria.")
    except ValueError:
        errores.append("Fecha: fecha inválida, usá dd/mm/aaaa.")
        v["fecha"] = None
    for t in TABLAS:
        v[t] = _tabla(data, t, errores)
    for k in CAMPOS_TEXTO:
        if not v[k]:
            errores.append(f"{CAMPO_LABELS[k]}: es obligatorio.")
    ps = json.loads(v["participantes"])
    if not ps:
        errores.append("Cargá al menos un participante.")
    elif not any(p.get("asistencia") == "Presente" for p in ps):
        errores.append("Al menos un participante tiene que estar presente.")
    if not json.loads(v["acciones"]):
        errores.append("Cargá al menos una acción o conclusión, con responsable y fecha.")
    return v, errores


def _fmt(campo: str, val: Any) -> Any:
    if not val:
        return val
    if campo == "fecha":
        return fecha_dmy(val)
    if campo in TABLAS:
        return "\n".join(" · ".join(f.get(k, "") or "—" for k in TABLAS[campo]) for f in json.loads(val)) or None
    return val


def sincronizar_plan(m: MinutaReunion, user_id: int | None) -> int:
    """Cada acción de la minuta con responsable es una acción del Plan de acción (QDV-RG-PG-02_03).

    Los renglones sin responsable son conclusiones y no pasan al plan. Devuelve cuántas acciones creó.
    """
    filas_ = filas(m, "acciones")
    base = {"origen": "Minuta de reunión", "fecha_deteccion": m.fecha, "requisito": f"{REGISTRO['codigo']} Minuta N° {m.numero}"}
    creadas = plan.sincronizar_filas(filas_, base, user_id)
    m.acciones = json.dumps(filas_, ensure_ascii=False)
    return creadas


def plan_numeros(m: MinutaReunion | None) -> dict[int, int]:
    """id de acción del plan → su N°, para los renglones de la minuta que ya están en el plan."""
    return plan.numeros([f["plan_accion_id"] for f in filas(m, "acciones") if f.get("plan_accion_id")])


def _sin_firmas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in f.items() if k not in FIRMA_CAMPOS} for f in rows]


def guardar(m: MinutaReunion, data: Any, user_id: int | None) -> tuple[list[str], bool]:
    """(errores, cambió). Si cambió algo, las firmas que había se anulan: hay que volver a firmar."""
    v, errores = _limpio(data)
    if errores:
        return errores, False
    nuevas = json.loads(v["acciones"])
    plan.conservar_ids(filas(m, "acciones"), nuevas)
    v["acciones"] = json.dumps(nuevas, ensure_ascii=False)
    anteriores = filas(m, "participantes")
    ps = _vincular(json.loads(v["participantes"]))
    por_user = {f["user_id"]: f for f in anteriores if f.get("user_id") and f.get("firma_at")}
    for f in ps:  # conservar la firma de quien sigue presente (se anula abajo si cambió algo)
        prev = por_user.get(f.get("user_id"))
        if prev is not None and f.get("asistencia") == "Presente":
            f.update({k: prev[k] for k in FIRMA_CAMPOS if prev.get(k)})
    v["participantes"] = json.dumps(ps, ensure_ascii=False)
    cambio = False
    for campo, nuevo in v.items():
        antes = getattr(m, campo)
        if campo in TABLAS:
            if campo == "participantes" and _sin_firmas(json.loads(antes or "[]")) == _sin_firmas(json.loads(nuevo)):
                continue
            if json.loads(antes or "[]") == json.loads(nuevo):
                continue
        elif (antes or None) == (nuevo or None):
            continue
        setattr(m, campo, nuevo)
        cambio = True
        _log(m, user_id, campo, _fmt(campo, antes), _fmt(campo, nuevo))
    firmadas = [f for f in anteriores if f.get("firma_at")]
    if cambio and firmadas:
        m.participantes = json.dumps(_sin_firmas(filas(m, "participantes")), ensure_ascii=False)
        _log(m, user_id, "firmas", "Firmada por: " + ", ".join(f["participante"] for f in firmadas),
             "Anuladas porque se modificó la minuta: tienen que volver a firmar.")
    return [], cambio


def crear(data: Any, user_id: int | None) -> tuple[MinutaReunion | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    numero = (db.session.scalar(select(func.max(MinutaReunion.numero))) or 0) + 1
    v["participantes"] = json.dumps(_vincular(json.loads(v["participantes"])), ensure_ascii=False)
    m = MinutaReunion(numero=numero, **v)
    db.session.add(m)
    db.session.flush()
    _log(m, user_id, "alta", None, f"N° {numero}: {m.motivo}")
    return m, []


def baja(m: MinutaReunion, user_id: int | None) -> None:
    m.activo = False
    _log(m, user_id, "baja", f"N° {m.numero}: {m.motivo}", None)


# ------------------------------------------------------------------ firmas


def _norm(nombre: str) -> str:
    txt = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode().lower()
    return " ".join(sorted(re.sub(r"[^a-z0-9 ]", " ", txt).split()))


def usuarios_activos() -> list[User]:
    return list(db.session.scalars(select(User).where(User.activo.is_(True)).order_by(User.nombre_completo)))


def nombres_usuarios() -> list[str]:
    """Para sugerir el participante: el nombre tal como está en el usuario del sistema."""
    return [u.nombre_completo.strip() for u in usuarios_activos() if (u.nombre_completo or "").strip()]


def usuario_de(nombre: str) -> User | None:
    """Usuario activo con ese nombre («Aun, Silvio Fernando» = «Silvio Fernando Aun»); None si no hay uno solo."""
    clave = _norm(nombre)
    if not clave:
        return None
    hallados = [u for u in usuarios_activos() if clave in (_norm(u.nombre_completo or ""), _norm(u.username or ""))]
    return hallados[0] if len(hallados) == 1 else None


def _vincular(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for f in rows:
        u = usuario_de(f.get("participante", ""))
        f.pop("user_id", None)
        if u is not None:
            f["user_id"] = int(u.id)
    return rows


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def firma_texto(fila: dict[str, Any]) -> str:
    """Columna FIRMA: la firma en el sistema reemplaza a la firma en papel."""
    if fila.get("asistencia") != "Presente":
        return "No firma (ausente)"
    if not fila.get("user_id"):
        return "Sin usuario del sistema"
    if not fila.get("firma_at"):
        return "Pendiente de firma"
    cuando = fecha_local(datetime.fromisoformat(fila["firma_at"]))
    via = fila.get("firma_via") or "sistema"
    return f"Firmado en el sistema ({via}) · {cuando}"


def pendientes_de_firma(m: MinutaReunion) -> list[User]:
    out = []
    for f in filas(m, "participantes"):
        if f.get("asistencia") == "Presente" and f.get("user_id") and not f.get("firma_at"):
            u = db.session.get(User, int(f["user_id"]))
            if u is not None and u.activo:
                out.append(u)
    return out


def firmas(m: MinutaReunion) -> tuple[int, int]:
    """(firmadas, a firmar) entre los presentes con usuario."""
    ps = [f for f in filas(m, "participantes") if f.get("asistencia") == "Presente" and f.get("user_id")]
    return sum(1 for f in ps if f.get("firma_at")), len(ps)


def puede_firmar(m: MinutaReunion, user: User | None) -> bool:
    return user is not None and any(int(u.id) == int(user.id) for u in pendientes_de_firma(m))


def firmar(m: MinutaReunion, user: User, via: str = "sistema") -> str:
    if not m.activo:
        raise ValueError("La minuta fue dada de baja.")
    rows = filas(m, "participantes")
    fila = next((f for f in rows if f.get("user_id") == int(user.id) and f.get("asistencia") == "Presente"), None)
    if fila is None:
        raise ValueError("No figurás como participante presente de esta minuta.")
    if fila.get("firma_at"):
        raise ValueError("Ya firmaste esta minuta.")
    fila["firma_at"] = _ahora_iso()
    fila["firma_via"] = via
    m.participantes = json.dumps(rows, ensure_ascii=False)
    _log(m, int(user.id), "firma", None, f"Firmó {fila['participante']} ({via})")
    from app.services import security_audit_service as audit_svc

    audit_svc.record_event(action="minuta_firmada", module="sgi", actor=user, entity_type="minuta_reunion",
                           entity_id=m.id, detail=f"Minuta N° {m.numero} ({via})")
    return f"Listo, firmaste la Minuta de reunión N° {m.numero}."


def texto_minuta(m: MinutaReunion) -> str:
    """La minuta completa en texto, para leerla en el aviso antes de firmar."""
    ps = "\n".join(f"- {p['participante']} ({p['sector']}): {p['asistencia']}" for p in filas(m, "participantes"))
    acs = "\n".join(f"- {a['accion']} · {a['responsable']} · {a['fecha']}" for a in filas(m, "acciones"))
    return (
        f"Minuta de reunión N° {m.numero} ({REGISTRO['codigo']})\n"
        f"Fecha: {fecha_dmy(m.fecha) if m.fecha else ''} · Horario: {m.horario} · Lugar: {m.lugar}\n"
        f"Motivo: {m.motivo}\n\nParticipantes:\n{ps}\n\nDesarrollo:\n{m.desarrollo}\n\n"
        f"Acciones / conclusiones:\n{acs}"
    )


def avisar_firmas(app: Any, m: MinutaReunion, excluir_user_id: int | None = None) -> int:
    """Pide la firma a cada presente que falta (mail con link y copia por WhatsApp). Devuelve a cuántos avisó."""
    from app.services import accion_link_service as accion_svc
    from app.services.mail_service import enviar_mail, is_mail_fully_configured
    from app.services.sgi_difusion_mail_service import _user_emails

    if not is_mail_fully_configured(app):
        log.warning("Minuta %s: SMTP no configurado, no se piden firmas", m.id)
        return 0
    texto = texto_minuta(m)
    avisados = 0
    for u in pendientes_de_firma(m):
        if excluir_user_id is not None and int(u.id) == int(excluir_user_id):
            continue
        mails = _user_emails(u)
        if not mails:
            continue
        link = accion_svc.url(app, accion_svc.MINUTA_FIRMAR, m.id, email=mails[0], user_id=int(u.id))
        try:
            enviar_mail(
                app,
                destinatarios=[mails[0]],
                asunto=f"QDV SGI — Firmar la Minuta de reunión N° {m.numero}",
                cuerpo_html=(
                    f"<p>Participaste de la reunión del {html_lib.escape(fecha_dmy(m.fecha) if m.fecha else '')} y te toca "
                    "<strong>firmar la minuta</strong>. Leela:</p>"
                    f'<pre style="white-space:pre-wrap;font-family:inherit">{html_lib.escape(texto)}</pre>'
                    f'<p><a href="{html_lib.escape(link)}"><strong>Firmar la minuta</strong></a> '
                    "(desde el celular, sin entrar al sistema)</p>"
                ),
                cuerpo_texto=f"Te toca firmar la minuta de la reunión. Leela:\n\n{texto}\n\nFirmar la minuta: {link}",
                texto_whatsapp=(
                    f"Te toca firmar la Minuta de reunión N° {m.numero}. Leela:\n\n{texto}\n\n"
                    "Si está bien, respondeme *FIRMAR*. Si hay algo para corregir, avisale a quien la cargó."
                ),
            )
            avisados += 1
        except Exception:
            log.exception("Minuta %s: falló el aviso de firma a %s", m.id, mails[0])
    return avisados
