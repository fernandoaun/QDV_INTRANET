"""Minuta de revisión por la dirección (registro SGI QDV-RG-PG-07_01, procedimiento PG-07).

Misma estructura que el formulario Word: N° y fecha, los temas de entrada de la revisión (los de las normas,
9.3.2), los participantes con su cargo y lo tratado en cada tema. Se agregan las decisiones y acciones que salen
de la revisión (9.3.3): cada una con responsable pasa al Plan de acción, como en la minuta de reunión.

Todos los campos son obligatorios: si un tema no tuvo novedades se escribe así («Sin cambios en el período»). Cada
participante con usuario del sistema firma desde la hoja o desde el aviso (mail con link o WhatsApp), igual que la
minuta de reunión; si la minuta se modifica, las firmas se anulan.
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models import RevisionDireccion, RevisionDireccionCambio, User
from app.services import plan_accion_service as plan
from app.services.fichas_proceso_service import fecha_local
from app.services.minuta_reunion_service import nombres_usuarios, usuario_de
from app.services.plan_accion_service import fecha_dmy, parse_fecha

log = logging.getLogger(__name__)

REGISTRO = {
    "codigo": "QDV-RG-PG-07_01",
    "titulo": "MINUTA DE REVISIÓN POR LA DIRECCIÓN",
    "fecha_vigencia": date(2026, 11, 24),
    "revision": "00",
}
CONTROL_CAMBIOS: tuple[tuple[str, str, str], ...] = (("00", "Confección del formulario", "24/11/2026"),)

# Temas del formulario, en su orden. (clave, texto, nivel): nivel 0 = tema; 1 = ítem dentro del tema anterior.
# Los encabezados sin clave («La información sobre el desempeño…») agrupan ítems y no llevan texto propio.
TEMAS: tuple[tuple[str | None, str, int], ...] = (
    ("estado_acciones", "Estado de acciones de revisiones por la dirección previas", 0),
    ("cuestiones", "Cambios en las cuestiones externas e internas que sean pertinentes al sistema de gestión integrado", 0),
    ("partes_interesadas", "Las necesidades y expectativas de las partes interesadas, incluidos los requisitos legales y otros requisitos", 1),
    ("aspectos_ambientales", "Sus aspectos ambientales significativos", 1),
    ("riesgos_oportunidades", "Los riesgos y oportunidades", 1),
    (None, "La información sobre el desempeño y eficacia del sistema de gestión integrado, incluidas las tendencias relativas a:", 0),
    ("satisfaccion_cliente", "La satisfacción del cliente y la retroalimentación de las partes interesadas pertinentes", 1),
    ("objetivos", "El grado en el que se han logrado los objetivos del SGI", 1),
    ("desempeno_procesos", "El desempeño de los procesos y la conformidad de los productos y servicios", 1),
    ("nc_acciones", "Las no conformidades y acciones correctivas", 1),
    ("auditorias", "Los resultados de las auditorías", 1),
    ("proveedores", "El desempeño de los proveedores externos", 1),
    ("recursos", "La adecuación de los recursos", 0),
    ("eficacia_riesgos", "La eficacia de las acciones tomadas para abordar los riesgos y las oportunidades", 0),
    ("mejora", "Las oportunidades de mejora continua", 0),
    (None, "La información sobre el desempeño ambiental de la organización, incluidas las tendencias relativas a:", 0),
    ("amb_nc", "No conformidades y acciones correctivas", 1),
    ("amb_seguimiento", "Resultados de seguimiento y medición", 1),
    ("amb_legales", "Cumplimiento de los requisitos legales y otros requisitos", 1),
    ("amb_auditorias", "Resultados de auditorías", 1),
    ("comunicaciones", "Las comunicaciones pertinentes a las partes interesadas, incluidas las quejas", 0),
    ("participacion", "Los resultados de la participación y consulta", 0),
    ("syso", "El desempeño SYSO de la organización", 0),
    ("incidentes", "El estado de la investigación de incidentes", 0),
    ("otros", "Otros", 0),
)
CLAVES_TEMAS: tuple[str, ...] = tuple(k for k, _, _ in TEMAS if k)
TEMA_LABELS: dict[str, str] = {k: t for k, t, _ in TEMAS if k}
TABLAS: dict[str, tuple[str, ...]] = {
    "participantes": ("participante", "cargo"),
    "acciones": ("accion", "responsable", "fecha"),
}
FILAS: dict[str, int] = {"participantes": 8, "acciones": 3}
FIRMA_CAMPOS: tuple[str, ...] = ("firma_at", "firma_via")
CAMPO_LABELS: dict[str, str] = {
    "numero": "Minuta N°",
    "fecha": "Fecha",
    "temas": "Temas tratados",
    "participantes": "Participantes",
    "acciones": "Decisiones y acciones",
    "alta": "Alta",
    "baja": "Baja",
    "firma": "Firma",
    "firmas": "Firmas",
}


def temas(r: RevisionDireccion | None) -> dict[str, str]:
    if r is None:
        return {}
    try:
        data = json.loads(r.temas or "{}")
    except ValueError:
        return {}
    return {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def filas(r: RevisionDireccion | None, tabla: str) -> list[dict[str, Any]]:
    if r is None:
        return []
    try:
        data = json.loads(getattr(r, tabla) or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)]


def labels_context() -> dict[str, Any]:
    return {
        "reg": REGISTRO, "temas_op": TEMAS, "rd_campo_labels": CAMPO_LABELS, "fecha_local": fecha_local, "fecha_dmy": fecha_dmy,
        "temas": temas, "filas": filas, "filas_min": FILAS, "firma_texto": firma_texto, "control_cambios": CONTROL_CAMBIOS,
        "plan_numeros": plan_numeros,
    }


def listar() -> list[RevisionDireccion]:
    return list(
        db.session.scalars(
            select(RevisionDireccion).where(RevisionDireccion.activo.is_(True)).order_by(RevisionDireccion.numero.desc())
        )
    )


def get(revision_id: int) -> RevisionDireccion | None:
    r = db.session.get(RevisionDireccion, int(revision_id))
    return r if r is not None and r.activo else None


def cambios(r: RevisionDireccion, limit: int = 100) -> list[RevisionDireccionCambio]:
    return list(
        db.session.scalars(
            select(RevisionDireccionCambio)
            .where(RevisionDireccionCambio.revision_id == r.id)
            .order_by(RevisionDireccionCambio.created_at.desc(), RevisionDireccionCambio.id.desc())
            .limit(limit)
        ).unique()
    )


def _log(r: RevisionDireccion, user_id: int | None, campo: str, antes: Any, despues: Any) -> None:
    db.session.add(
        RevisionDireccionCambio(
            revision_id=r.id,
            user_id=user_id,
            campo=campo,
            antes=None if antes in (None, "") else str(antes),
            despues=None if despues in (None, "") else str(despues),
        )
    )


def _tabla(data: Any, tabla: str, errores: list[str]) -> list[dict[str, Any]]:
    """Renglones desde el formulario (<tabla>_<campo>_<i>) o desde una lista; descarta los vacíos."""
    campos = TABLAS[tabla]
    if hasattr(data, "getlist"):
        crudas = [
            {**{k: data.get(f"{tabla}_{k}_{i}") for k in campos}, "plan_accion_id": data.get(f"{tabla}_plan_{i}")}
            for i in range(int(data.get(f"{tabla}_filas") or 0))
        ]
    else:
        crudas = list(data.get(tabla) or [])
    out: list[dict[str, Any]] = []
    for i, cruda in enumerate(crudas):
        fila: dict[str, Any] = {k: re.sub(r"\s+", " ", str(cruda.get(k) or "")).strip()[:255] for k in campos}
        if not any(fila.values()):
            continue
        if not all(fila.values()):
            errores.append(f"{CAMPO_LABELS[tabla]}, renglón {i + 1}: completá todas las columnas.")
        if fila.get("fecha"):
            try:
                fila["fecha"] = fecha_dmy(parse_fecha(fila["fecha"]))
            except ValueError:
                errores.append(f"{CAMPO_LABELS[tabla]}, renglón {i + 1}: fecha inválida, usá dd/mm/aaaa.")
        if str(cruda.get("plan_accion_id") or "").isdigit():
            fila["plan_accion_id"] = int(cruda["plan_accion_id"])
        out.append(fila)
    return out


def _limpio(data: Any) -> tuple[dict[str, Any], list[str]]:
    errores: list[str] = []
    v: dict[str, Any] = {}
    try:
        v["fecha"] = parse_fecha(data.get("fecha"))
        if v["fecha"] is None:
            errores.append("Fecha: es obligatoria.")
    except ValueError:
        errores.append("Fecha: fecha inválida, usá dd/mm/aaaa.")
        v["fecha"] = None
    crudos = data.get("temas") if isinstance(data.get("temas"), dict) else {}
    ts: dict[str, str] = {}
    faltan = []
    for k in CLAVES_TEMAS:
        val = str((crudos.get(k) if crudos else data.get(f"tema_{k}")) or "").strip()
        ts[k] = val
        if not val:
            faltan.append(TEMA_LABELS[k])
    if faltan:
        errores.append("Completá todos los temas (si no hubo novedades, escribilo): " + "; ".join(faltan) + ".")
    v["temas"] = json.dumps(ts, ensure_ascii=False)
    ps = _tabla(data, "participantes", errores)
    if not ps:
        errores.append("Cargá al menos un participante, con su cargo.")
    v["participantes"] = json.dumps(ps, ensure_ascii=False)
    acs = _tabla(data, "acciones", errores)
    if not acs:
        errores.append("Cargá al menos una decisión o acción, con responsable y fecha.")
    v["acciones"] = json.dumps(acs, ensure_ascii=False)
    return v, errores


def _fmt(campo: str, val: Any) -> Any:
    if not val:
        return val
    if campo == "fecha":
        return fecha_dmy(val)
    if campo == "temas":
        return "\n".join(f"{TEMA_LABELS.get(k, k)}: {t}" for k, t in json.loads(val).items()) or None
    if campo in TABLAS:
        return "\n".join(" · ".join(f.get(k, "") or "—" for k in TABLAS[campo]) for f in json.loads(val)) or None
    return val


def sincronizar_plan(r: RevisionDireccion, user_id: int | None) -> int:
    """Cada decisión o acción con responsable es una acción del Plan de acción (QDV-RG-PG-02_03)."""
    filas_ = filas(r, "acciones")
    base = {"origen": "Minuta de reunión", "fecha_deteccion": r.fecha,
            "requisito": f"{REGISTRO['codigo']} Revisión por la dirección N° {r.numero}",
            "tipo_hallazgo": "Otros", "tipo_accion": "Acción de control", "causa_raiz": "No aplica"}
    creadas = plan.sincronizar_filas(filas_, base, user_id)
    r.acciones = json.dumps(filas_, ensure_ascii=False)
    return creadas


def plan_numeros(r: RevisionDireccion | None) -> dict[int, int]:
    return plan.numeros([f["plan_accion_id"] for f in filas(r, "acciones") if f.get("plan_accion_id")])


def _sin_firmas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in f.items() if k not in FIRMA_CAMPOS} for f in rows]


def _vincular(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for f in rows:
        u = usuario_de(f.get("participante", ""))
        f.pop("user_id", None)
        if u is not None:
            f["user_id"] = int(u.id)
    return rows


def guardar(r: RevisionDireccion, data: Any, user_id: int | None) -> tuple[list[str], bool]:
    """(errores, cambió). Si cambió algo, las firmas que había se anulan: hay que volver a firmar."""
    v, errores = _limpio(data)
    if errores:
        return errores, False
    nuevas = json.loads(v["acciones"])
    plan.conservar_ids(filas(r, "acciones"), nuevas)
    v["acciones"] = json.dumps(nuevas, ensure_ascii=False)
    anteriores = filas(r, "participantes")
    ps = _vincular(json.loads(v["participantes"]))
    por_user = {f["user_id"]: f for f in anteriores if f.get("user_id") and f.get("firma_at")}
    for f in ps:
        prev = por_user.get(f.get("user_id"))
        if prev is not None:
            f.update({k: prev[k] for k in FIRMA_CAMPOS if prev.get(k)})
    v["participantes"] = json.dumps(ps, ensure_ascii=False)
    cambio = False
    for campo, nuevo in v.items():
        antes = getattr(r, campo)
        if campo == "participantes":
            if _sin_firmas(json.loads(antes or "[]")) == _sin_firmas(json.loads(nuevo)):
                continue
        elif campo in ("temas", "acciones"):
            if json.loads(antes or "null") == json.loads(nuevo):
                continue
        elif (antes or None) == (nuevo or None):
            continue
        setattr(r, campo, nuevo)
        cambio = True
        _log(r, user_id, campo, _fmt(campo, antes), _fmt(campo, nuevo))
    firmadas = [f for f in anteriores if f.get("firma_at")]
    if cambio and firmadas:
        r.participantes = json.dumps(_sin_firmas(filas(r, "participantes")), ensure_ascii=False)
        _log(r, user_id, "firmas", "Firmada por: " + ", ".join(f["participante"] for f in firmadas),
             "Anuladas porque se modificó la minuta: tienen que volver a firmar.")
    return [], cambio


def crear(data: Any, user_id: int | None) -> tuple[RevisionDireccion | None, list[str]]:
    v, errores = _limpio(data)
    if errores:
        return None, errores
    numero = (db.session.scalar(select(func.max(RevisionDireccion.numero))) or 0) + 1
    v["participantes"] = json.dumps(_vincular(json.loads(v["participantes"])), ensure_ascii=False)
    r = RevisionDireccion(numero=numero, **v)
    db.session.add(r)
    db.session.flush()
    _log(r, user_id, "alta", None, f"N° {numero} del {fecha_dmy(r.fecha)}")
    return r, []


def baja(r: RevisionDireccion, user_id: int | None) -> None:
    r.activo = False
    _log(r, user_id, "baja", f"N° {r.numero} del {fecha_dmy(r.fecha) if r.fecha else ''}", None)


# ------------------------------------------------------------------ firmas


def firma_texto(fila: dict[str, Any]) -> str:
    if not fila.get("user_id"):
        return "Sin usuario del sistema"
    if not fila.get("firma_at"):
        return "Pendiente de firma"
    cuando = fecha_local(datetime.fromisoformat(fila["firma_at"]))
    return f"Firmado en el sistema ({fila.get('firma_via') or 'sistema'}) · {cuando}"


def pendientes_de_firma(r: RevisionDireccion) -> list[User]:
    out = []
    for f in filas(r, "participantes"):
        if f.get("user_id") and not f.get("firma_at"):
            u = db.session.get(User, int(f["user_id"]))
            if u is not None and u.activo:
                out.append(u)
    return out


def firmas(r: RevisionDireccion) -> tuple[int, int]:
    ps = [f for f in filas(r, "participantes") if f.get("user_id")]
    return sum(1 for f in ps if f.get("firma_at")), len(ps)


def puede_firmar(r: RevisionDireccion, user: User | None) -> bool:
    return user is not None and r.activo and any(int(u.id) == int(user.id) for u in pendientes_de_firma(r))


def firmar(r: RevisionDireccion, user: User, via: str = "sistema") -> str:
    if not r.activo:
        raise ValueError("La minuta fue dada de baja.")
    rows = filas(r, "participantes")
    fila = next((f for f in rows if f.get("user_id") == int(user.id)), None)
    if fila is None:
        raise ValueError("No figurás como participante de esta minuta.")
    if fila.get("firma_at"):
        raise ValueError("Ya firmaste esta minuta.")
    fila["firma_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fila["firma_via"] = via
    r.participantes = json.dumps(rows, ensure_ascii=False)
    _log(r, int(user.id), "firma", None, f"Firmó {fila['participante']} ({via})")
    from app.services import security_audit_service as audit_svc

    audit_svc.record_event(action="revision_direccion_firmada", module="sgi", actor=user, entity_type="revision_direccion",
                           entity_id=r.id, detail=f"Revisión por la dirección N° {r.numero} ({via})")
    return f"Listo, firmaste la Minuta de revisión por la dirección N° {r.numero}."


def texto_revision(r: RevisionDireccion) -> str:
    """La minuta completa en texto, para leerla en el aviso antes de firmar."""
    ts = temas(r)
    lineas = []
    for k, t, nivel in TEMAS:
        if k is None:
            lineas.append(f"\n{t}")
        else:
            lineas.append(f"{'  ' if nivel else ''}- {t}: {ts.get(k, '')}")
    ps = "\n".join(f"- {p['participante']} ({p['cargo']})" for p in filas(r, "participantes"))
    acs = "\n".join(f"- {a['accion']} · {a['responsable']} · {a['fecha']}" for a in filas(r, "acciones"))
    return (
        f"Minuta de revisión por la dirección N° {r.numero} ({REGISTRO['codigo']})\n"
        f"Fecha: {fecha_dmy(r.fecha) if r.fecha else ''}\n\nParticipantes:\n{ps}\n\nTemas tratados:\n"
        + "\n".join(lineas) + f"\n\nDecisiones y acciones:\n{acs}"
    )


def avisar_firmas(app: Any, r: RevisionDireccion, excluir_user_id: int | None = None) -> int:
    """Pide la firma a cada participante que falta (mail con link y copia por WhatsApp). Devuelve a cuántos avisó."""
    from app.services import accion_link_service as accion_svc
    from app.services.mail_service import enviar_mail, is_mail_fully_configured
    from app.services.sgi_difusion_mail_service import _user_emails

    if not is_mail_fully_configured(app):
        log.warning("Revisión por la dirección %s: SMTP no configurado, no se piden firmas", r.id)
        return 0
    texto = texto_revision(r)
    avisados = 0
    for u in pendientes_de_firma(r):
        if excluir_user_id is not None and int(u.id) == int(excluir_user_id):
            continue
        mails = _user_emails(u)
        if not mails:
            continue
        link = accion_svc.url(app, accion_svc.REVDIR_FIRMAR, r.id, email=mails[0], user_id=int(u.id))
        try:
            enviar_mail(
                app,
                destinatarios=[mails[0]],
                asunto=f"QDV SGI — Firmar la Minuta de revisión por la dirección N° {r.numero}",
                cuerpo_html=(
                    "<p>Participaste de la revisión por la dirección y te toca <strong>firmar la minuta</strong>. Leela:</p>"
                    f'<pre style="white-space:pre-wrap;font-family:inherit">{html_lib.escape(texto)}</pre>'
                    f'<p><a href="{html_lib.escape(link)}"><strong>Firmar la minuta</strong></a> '
                    "(desde el celular, sin entrar al sistema)</p>"
                ),
                cuerpo_texto=f"Te toca firmar la minuta de revisión por la dirección. Leela:\n\n{texto}\n\nFirmar: {link}",
                texto_whatsapp=(
                    f"Te toca firmar la Minuta de revisión por la dirección N° {r.numero}. Leela:\n\n{texto}\n\n"
                    "Si está bien, respondeme *FIRMAR*. Si hay algo para corregir, avisale a quien la cargó."
                ),
            )
            avisados += 1
        except Exception:
            log.exception("Revisión por la dirección %s: falló el aviso de firma a %s", r.id, mails[0])
    return avisados


