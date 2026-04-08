from __future__ import annotations

from typing import Any


def voltajes_display_items(value: Any) -> list[tuple[int, str]]:
    """
    Devuelve [(1, '3.2'), (2, '3.1'), ...] para renderizar V1, V2, … sin tocar el almacenamiento.
    Acepta listas (JSON habitual), strings separados por coma, o valores sueltos.
    """
    raw: list[Any] = []
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        raw = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
    else:
        try:
            raw = list(value)  # type: ignore[arg-type]
        except TypeError:
            raw = [value]
    out: list[tuple[int, str]] = []
    for i, x in enumerate(raw):
        if x is None or (isinstance(x, str) and not x.strip()):
            continue
        t = x.strip() if isinstance(x, str) else str(x).strip()
        out.append((i + 1, t))
    return out


def shift_operator_display_filter(sess) -> str:
    from app.services.shift_handover_service import format_shift_operator_display

    return format_shift_operator_display(sess) if sess is not None else ""


def es_hipoclorito_entrega_filter(value: Any) -> bool:
    from app.utils.hipoclorito_producto import es_producto_entrega_operativo_hipoclorito

    return es_producto_entrega_operativo_hipoclorito(str(value or ""))


def register_template_filters(app) -> None:
    app.jinja_env.filters["voltajes_display_items"] = voltajes_display_items
    app.jinja_env.filters["shift_operator_display"] = shift_operator_display_filter
    app.jinja_env.filters["es_hipoclorito_entrega"] = es_hipoclorito_entrega_filter
