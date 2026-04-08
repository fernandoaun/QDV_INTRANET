"""
Avisos operativos no bloqueantes reutilizables (salmuera/hipoclorito, reactor, agua).
Centraliza reglas para templates, API y cambio de turno.
"""
from __future__ import annotations

from app.models.domain import AguaRegistro, ReactorRegistro, SalmueraRegistro
from app.services.hipoclorito_warnings import evaluate_hipoclorito_operational_warnings


def warnings_for_salmuera_registro(r: SalmueraRegistro) -> list[str]:
    return evaluate_hipoclorito_operational_warnings(
        hipo_exceso_soda=float(r.hipo_exceso_soda),
        sal_conc=float(r.sal_conc),
        sal_ph=float(r.sal_ph),
        declor_ph=float(r.declor_ph),
    )


def warnings_for_reactor_registro(r: ReactorRegistro) -> list[str]:
    msgs: list[str] = []
    if float(r.exceso_naoh) > 0.16:
        msgs.append("Soda > 0.16")
    if float(r.exceso_na2co3) > 0.45:
        msgs.append("Carbonato > 0.45")
    if float(r.concentracion_tabla) < 200:
        msgs.append("Salmuera < 200")
    return msgs


def warnings_for_agua_registro(r: AguaRegistro) -> list[str]:
    if float(r.dureza) > 1.0:
        return ["Dureza > 1 ppm"]
    return []
