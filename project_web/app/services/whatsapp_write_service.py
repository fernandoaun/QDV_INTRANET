"""Cargas por WhatsApp/API: mismas reglas de permiso y turno que la web."""

from __future__ import annotations

import json
from typing import Any

from flask import current_app, has_request_context, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.auth_utils import (
    user_can,
    user_can_edit,
    user_can_edit_stock_consumos,
    user_can_edit_stock_ingreso_categoria,
    user_shift_may_write_operational,
)
from app.extensions import db
from app.models import AguaRegistro, ReactorRegistro, SalmueraRegistro, User
from app.services import security_audit_service as audit_svc
from app.services import stock_service
from app.web.modules.produccion.agua_helpers import agua_row_to_dict, next_agua_lote
from app.web.modules.produccion.operativa_context import (
    compute_turno_from_hour,
    default_operador_for_salmuera,
    now_local,
    operador_display_line,
)
from app.web.modules.produccion.reactor_helpers import next_reactor_lote, parse_required_float, reactor_row_to_dict
from app.web.modules.produccion.salmuera_helpers import (
    count_consecutive_single_cell_for_electrolizador,
    next_salmuera_lote,
    parse_voltajes,
    salmuera_row_to_dict,
)
from app.services.hipoclorito_warnings import (
    append_hipoclorito_warnings_to_observaciones,
    evaluate_hipoclorito_operational_warnings,
)

WRITE_MODULES = frozenset({"reactor", "agua", "salmuera", "stock_ingreso", "stock_consumo"})
OPERATIONAL_WRITE_MODULES = frozenset({"reactor", "agua", "salmuera", "stock_ingreso", "stock_consumo"})
INTENT_MAX_AGE_SEC = 600
_SALT = "qdv-whatsapp-intent-v1"


def _float(payload: dict[str, Any], key: str, label: str) -> float:
    raw = payload.get(key)
    if raw is None or str(raw).strip() == "":
        raise ValueError(f"{label} es obligatorio.")
    return parse_required_float(str(raw), label)


def _perm_for_module(module: str) -> str:
    return {
        "reactor": "reactor",
        "agua": "agua",
        "salmuera": "salmuera",
        "stock_ingreso": "stock_hub",
        "stock_consumo": "stock_consumos",
    }[module]


def assert_can_write(user: User, module: str) -> None:
    if module not in WRITE_MODULES:
        raise ValueError(f"Módulo de carga no disponible: {module}")
    if module == "stock_ingreso":
        if not (
            user_can_edit_stock_ingreso_categoria(user, "materia_prima")
            or user_can_edit_stock_ingreso_categoria(user, "laboratorio")
            or user_can_edit_stock_ingreso_categoria(user, "producto_terminado")
        ):
            raise PermissionError("Tu perfil no puede ingresar stock.")
    elif module == "stock_consumo":
        if not user_can_edit_stock_consumos(user):
            raise PermissionError("Tu perfil no puede cargar consumos de stock.")
    else:
        perm = _perm_for_module(module)
        if not user_can_edit(user, perm):
            raise PermissionError(f"Tu perfil no puede cargar {perm}.")
    sess = session if has_request_context() else None
    if module in OPERATIONAL_WRITE_MODULES and not user_shift_may_write_operational(user, sess):
        raise PermissionError("Necesitás turno de planta activo para cargar este dato.")


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(str(current_app.config["SECRET_KEY"]), salt=_SALT)


def _operador_label() -> str:
    return (operador_display_line() or default_operador_for_salmuera() or "").strip() or "whatsapp"


def preview_and_token(user: User, module: str, payload: dict[str, Any], source: str) -> dict[str, Any]:
    assert_can_write(user, module)
    summary, normalized = _validate(user, module, payload)
    token = _serializer().dumps(
        {"uid": int(user.id), "module": module, "payload": normalized, "source": (source or "texto")[:16]}
    )
    return {
        "ok": True,
        "needs_confirm": True,
        "confirm_token": token,
        "expires_in_seconds": INTENT_MAX_AGE_SEC,
        "module": module,
        "resumen": summary,
        "payload": normalized,
        "message": "Revisá el resumen y confirmá para guardar.",
    }


def confirm_and_save(user: User, token: str) -> dict[str, Any]:
    try:
        data = _serializer().loads(token, max_age=INTENT_MAX_AGE_SEC)
    except SignatureExpired as exc:
        raise ValueError("La confirmación venció. Armá de nuevo la carga.") from exc
    except BadSignature as exc:
        raise ValueError("Token de confirmación inválido.") from exc
    if int(data.get("uid") or 0) != int(user.id):
        raise PermissionError("Esa confirmación no es de tu usuario.")
    module = str(data.get("module") or "")
    payload = data.get("payload") or {}
    source = str(data.get("source") or "texto")
    assert_can_write(user, module)
    result = _execute(user, module, payload)
    audit_svc.record_event(
        action="whatsapp_carga",
        module=module,
        actor=user,
        entity_type=module,
        entity_id=int(result.get("id") or 0) or None,
        new_value=audit_svc.coerce_text(json.dumps(normalized_payload(payload), ensure_ascii=False)),
        detail=f"source={source}",
    )
    result["ok"] = True
    result["module"] = module
    return result


def normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {str(k): payload[k] for k in sorted(payload) if payload[k] is not None}


def _validate(user: User, module: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if module == "reactor":
        row = _reactor_fields(payload)
        resumen = (
            f"Reactor lote auto · pH {row['ph']} · temp {row['temperatura']} · "
            f"densidad {row['densidad']} · ORP {row['orp']}"
        )
        return resumen, row
    if module == "agua":
        row = _agua_fields(payload)
        resumen = f"Agua columna {row['numero_columna']} · temp {row['temperatura']} · dureza {row['dureza']}"
        return resumen, row
    if module == "salmuera":
        row = _salmuera_fields(payload)
        resumen = (
            f"Hipoclorito E{row['electrolizador']} · {row['cantidad_celdas']} celdas · "
            f"hipo {row['hipo_conc']} · pH sal {row['sal_ph']}"
        )
        return resumen, row
    if module == "stock_ingreso":
        row = _stock_ingreso_fields(user, payload)
        resumen = f"Ingreso {row['categoria']} {row['producto']} {row['marca']} · {row['cantidad']} · lote {row['lote']}"
        return resumen, row
    if module == "stock_consumo":
        row = _stock_consumo_fields(payload)
        resumen = f"Consumo {row['categoria']} {row['producto']} {row['marca']} · {row['cantidad']}"
        return resumen, row
    raise ValueError("Módulo desconocido.")


def _execute(user: User, module: str, payload: dict[str, Any]) -> dict[str, Any]:
    now = now_local()
    fecha = now.strftime("%Y-%m-%d")
    op = _operador_label()
    if module == "reactor":
        fields = _reactor_fields(payload)
        rec = ReactorRegistro(
            fecha_iso=fecha,
            hora_hm=now.strftime("%H:%M"),
            operador=op,
            lote=next_reactor_lote(fecha),
            observaciones=(fields.get("observaciones") or "") or None,
            created_at_iso=now.isoformat(timespec="seconds"),
            **{k: v for k, v in fields.items() if k != "observaciones"},
        )
        db.session.add(rec)
        db.session.commit()
        return {"id": rec.id, "message": "Reactor guardado.", "registro": reactor_row_to_dict(rec)}
    if module == "agua":
        fields = _agua_fields(payload)
        rec = AguaRegistro(
            fecha_iso=fecha,
            hora_hm=now.strftime("%H:%M"),
            turno=compute_turno_from_hour(now.strftime("%H:%M")),
            operador=op,
            lote=next_agua_lote(fecha),
            numero_columna=int(fields["numero_columna"]),
            temperatura=float(fields["temperatura"]),
            dureza=float(fields["dureza"]),
            observaciones=(fields.get("observaciones") or "") or None,
            created_at_iso=now.isoformat(timespec="seconds"),
        )
        db.session.add(rec)
        db.session.commit()
        return {"id": rec.id, "message": "Agua guardada.", "registro": agua_row_to_dict(rec)}
    if module == "salmuera":
        fields = _salmuera_fields(payload)
        rec = SalmueraRegistro(
            fecha_iso=fecha,
            hora_hm=now.strftime("%H:%M"),
            turno=compute_turno_from_hour(now.strftime("%H:%M")),
            operador=op,
            lote=next_salmuera_lote(fecha),
            voltajes_json=json.dumps(fields["voltajes"], ensure_ascii=False),
            voltaje_total=float(sum(fields["voltajes"])),
            created_at_iso=now.isoformat(timespec="seconds"),
            electrolizador=int(fields["electrolizador"]),
            cantidad_celdas=int(fields["cantidad_celdas"]),
            voltaje_total_trafo=float(fields["voltaje_total_trafo"]),
            amperaje=float(fields["amperaje"]),
            caudal_agua_l_h=float(fields["caudal_agua_l_h"]),
            caudal_salmuera_l_h=float(fields["caudal_salmuera_l_h"]),
            hipo_conc=float(fields["hipo_conc"]),
            hipo_exceso_soda=float(fields["hipo_exceso_soda"]),
            sal_temp=float(fields["sal_temp"]),
            sal_conc=float(fields["sal_conc"]),
            sal_ph=float(fields["sal_ph"]),
            soda_conc=float(fields["soda_conc"]),
            declor_ph=float(fields["declor_ph"]),
            orp=fields.get("orp"),
            observaciones=fields.get("observaciones") or None,
            atraso_motivo=(fields.get("atraso_motivo") or "") or None,
        )
        db.session.add(rec)
        db.session.commit()
        return {"id": rec.id, "message": "Hipoclorito/salmuera guardado.", "registro": salmuera_row_to_dict(rec)}
    if module == "stock_ingreso":
        fields = _stock_ingreso_fields(user, payload)
        stock_service.save_ingreso(
            fields["categoria"],
            fields["producto"],
            fields["marca"],
            fields["vencimiento"],
            fields["lote"],
            float(fields["cantidad"]),
            op,
            cargado_por_user_id=int(user.id),
        )
        return {"id": None, "message": "Ingreso de stock guardado.", "registro": fields}
    if module == "stock_consumo":
        fields = _stock_consumo_fields(payload)
        stock_service.save_consumo(
            fields["categoria"],
            fields["producto"],
            fields["marca"],
            float(fields["cantidad"]),
            op,
            observaciones=fields.get("observaciones") or "",
        )
        return {"id": None, "message": "Consumo de stock guardado.", "registro": fields}
    raise ValueError("Módulo desconocido.")


def _reactor_fields(payload: dict[str, Any]) -> dict[str, Any]:
    e2_temp = _float(payload, "e2_temperatura", "E2/E3 Temp")
    e2_den = _float(payload, "e2_densidad", "E2/E3 Densidad")
    e2_conc = _float(payload, "e2_concentracion", "E2/E3 Concentración")
    return {
        "ph": _float(payload, "ph", "pH"),
        "temperatura": _float(payload, "temperatura", "Temperatura"),
        "densidad": _float(payload, "densidad", "Densidad"),
        "concentracion_tabla": _float(payload, "concentracion_tabla", "Concentración tabla"),
        "exceso_naoh": _float(payload, "exceso_naoh", "Exceso NaOH"),
        "exceso_na2co3": _float(payload, "exceso_na2co3", "Exceso Na2CO3"),
        "orp": _float(payload, "orp", "ORP (mV)"),
        "e2_temperatura": e2_temp,
        "e2_densidad": e2_den,
        "e2_concentracion": e2_conc,
        "e3_temperatura": e2_temp,
        "e3_densidad": e2_den,
        "e3_concentracion": e2_conc,
        "observaciones": str(payload.get("observaciones") or "").strip(),
    }


def _agua_fields(payload: dict[str, Any]) -> dict[str, Any]:
    col = int(payload.get("numero_columna") or 1)
    if col < 1:
        raise ValueError("Número de columna inválido.")
    return {
        "numero_columna": col,
        "temperatura": _float(payload, "temperatura", "Temperatura"),
        "dureza": _float(payload, "dureza", "Dureza"),
        "observaciones": str(payload.get("observaciones") or "").strip(),
    }


def _salmuera_fields(payload: dict[str, Any]) -> dict[str, Any]:
    n = int(payload.get("cantidad_celdas") or 0)
    if n < 1 or n > 20:
        raise ValueError("Cantidad de celdas inválida.")
    electrolizador = int(payload.get("electrolizador") or 0)
    if electrolizador <= 0:
        raise ValueError("El electrolizador debe ser un número mayor a 0.")
    if n == 1 and count_consecutive_single_cell_for_electrolizador(electrolizador) >= 2:
        raise ValueError(
            "Para este electrolizador ya hay 2 cargas seguidas con 1 celda. La siguiente debe tener más de 1 celda."
        )
    volts_raw = payload.get("voltajes")
    if isinstance(volts_raw, list):
        volts_text = ",".join(str(v) for v in volts_raw)
    else:
        volts_text = str(volts_raw or "")
    volts = parse_voltajes(volts_text, n)
    if n == 1:
        if float(volts[0]) <= 0:
            raise ValueError("Con 1 celda, el voltaje debe ser mayor a 0.")
    else:
        for i, v in enumerate(volts, start=1):
            if v < 2.5 or v > 4.5:
                raise ValueError(f"Voltaje {i} fuera de rango (2.5 a 4.5).")
    caudal_agua = _float(payload, "caudal_agua_l_h", "Caudal agua")
    caudal_salmuera = _float(payload, "caudal_salmuera_l_h", "Caudal salmuera")
    if caudal_agua >= caudal_salmuera:
        raise ValueError("El caudal de agua debe ser menor que el caudal de salmuera.")
    hipo_exceso_soda = _float(payload, "hipo_exceso_soda", "Exceso soda")
    sal_conc = _float(payload, "sal_conc", "Conc. sal")
    sal_ph = _float(payload, "sal_ph", "pH sal")
    declor_ph = _float(payload, "declor_ph", "pH declor")
    orp = _float(payload, "orp", "ORP (mV)") if electrolizador == 2 else None
    obs = append_hipoclorito_warnings_to_observaciones(
        str(payload.get("observaciones") or "").strip(),
        evaluate_hipoclorito_operational_warnings(
            hipo_exceso_soda=hipo_exceso_soda,
            sal_conc=sal_conc,
            sal_ph=sal_ph,
            declor_ph=declor_ph,
        ),
    )
    return {
        "electrolizador": electrolizador,
        "cantidad_celdas": n,
        "voltajes": volts,
        "voltaje_total_trafo": _float(payload, "voltaje_total_trafo", "V total trafo"),
        "amperaje": _float(payload, "amperaje", "Amperaje"),
        "caudal_agua_l_h": caudal_agua,
        "caudal_salmuera_l_h": caudal_salmuera,
        "hipo_conc": _float(payload, "hipo_conc", "Hipo conc"),
        "hipo_exceso_soda": hipo_exceso_soda,
        "sal_temp": _float(payload, "sal_temp", "Temp sal"),
        "sal_conc": sal_conc,
        "sal_ph": sal_ph,
        "soda_conc": _float(payload, "soda_conc", "Conc. soda"),
        "declor_ph": declor_ph,
        "orp": orp,
        "observaciones": obs,
        "atraso_motivo": str(payload.get("atraso_motivo") or "").strip(),
    }


def _stock_ingreso_fields(user: User, payload: dict[str, Any]) -> dict[str, Any]:
    cat = str(payload.get("categoria") or "").strip()
    if cat not in ("materia_prima", "laboratorio", "producto_terminado"):
        raise ValueError("categoria debe ser materia_prima, laboratorio o producto_terminado.")
    if not user_can_edit_stock_ingreso_categoria(user, cat):
        raise PermissionError("Tu perfil no puede ingresar stock de esa categoría.")
    qty = _float(payload, "cantidad", "Cantidad")
    return {
        "categoria": cat,
        "producto": str(payload.get("producto") or "").strip(),
        "marca": str(payload.get("marca") or "").strip(),
        "vencimiento": str(payload.get("vencimiento") or "").strip(),
        "lote": str(payload.get("lote") or "").strip(),
        "cantidad": qty,
    }


def _stock_consumo_fields(payload: dict[str, Any]) -> dict[str, Any]:
    cat = str(payload.get("categoria") or "").strip()
    if cat not in ("materia_prima", "laboratorio", "producto_terminado"):
        raise ValueError("categoria debe ser materia_prima, laboratorio o producto_terminado.")
    return {
        "categoria": cat,
        "producto": str(payload.get("producto") or "").strip(),
        "marca": str(payload.get("marca") or "").strip(),
        "cantidad": _float(payload, "cantidad", "Cantidad"),
        "observaciones": str(payload.get("observaciones") or "").strip(),
    }


def capabilities(user: User) -> dict[str, Any]:
    sess = session if has_request_context() else None
    may_op = user_shift_may_write_operational(user, sess)
    cargas: dict[str, bool] = {}
    for mod in sorted(WRITE_MODULES):
        try:
            assert_can_write(user, mod)
            cargas[mod] = True
        except (PermissionError, ValueError):
            cargas[mod] = False
    return {
        "consultas": {
            "dashboard": True,
            "turno": True,
            "stock": user_can(user, "stock_existencias") or user_can(user, "stock_hub"),
            "entregas": user_can(user, "entregas"),
            "reactor": user_can(user, "reactor"),
            "agua": user_can(user, "agua"),
            "salmuera": user_can(user, "salmuera"),
            "personal": user_can(user, "personal"),
        },
        "cargas": cargas,
        "may_write_operational": bool(may_op),
    }
