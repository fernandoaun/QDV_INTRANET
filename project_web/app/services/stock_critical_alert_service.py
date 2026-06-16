"""Aviso por correo cuando un producto pasa a estado crítico de stock (por debajo del mínimo)."""

from __future__ import annotations

import html as html_lib
import logging
from typing import Any

from sqlalchemy import delete, select

from app.extensions import db
from app.models import ProductoCatalogo, StockCriticalAlertSent
from app.services.mail_service import enviar_mail, is_mail_fully_configured
from app.services.stock_alert_email_service import merged_recipient_addresses
from app.services.stock_service import _nivel_alerta_panel, stock_total_producto
from app.utils.datetime_operacion import now_operacion_local_iso_seconds

log = logging.getLogger(__name__)

_CATEGORIA_LABELS: dict[str, str] = {
    "materia_prima": "Materia prima",
    "producto_terminado": "Producto terminado",
    "laboratorio": "Laboratorio",
}


def _categoria_label(categoria: str) -> str:
    return _CATEGORIA_LABELS.get((categoria or "").strip(), categoria or "—")


def _get_minimo_alerta(categoria: str, producto: str) -> float | None:
    row = db.session.scalar(
        select(ProductoCatalogo).where(
            ProductoCatalogo.categoria == (categoria or "").strip(),
            ProductoCatalogo.nombre_producto == (producto or "").strip(),
            ProductoCatalogo.activo.is_(True),
            ProductoCatalogo.is_stockable.is_(True),
            ProductoCatalogo.stock_minimo_alerta.is_not(None),
        )
    )
    if row is None:
        return None
    try:
        return float(row.stock_minimo_alerta or 0)
    except (TypeError, ValueError):
        return None


def _sent_row(categoria: str, producto: str) -> StockCriticalAlertSent | None:
    return db.session.scalar(
        select(StockCriticalAlertSent).where(
            StockCriticalAlertSent.categoria == (categoria or "").strip(),
            StockCriticalAlertSent.producto == (producto or "").strip(),
        )
    )


def _clear_sent_if_exists(categoria: str, producto: str) -> None:
    db.session.execute(
        delete(StockCriticalAlertSent).where(
            StockCriticalAlertSent.categoria == (categoria or "").strip(),
            StockCriticalAlertSent.producto == (producto or "").strip(),
        )
    )


def _send_critical_mail(
    app: Any,
    *,
    categoria: str,
    producto: str,
    stock_actual: float,
    stock_minimo: float,
) -> None:
    recipients = merged_recipient_addresses(app)
    if not recipients:
        log.warning(
            "Stock crítico %s / %s: sin destinatarios STOCK_CRITICAL_ALERT_EMAIL",
            categoria,
            producto,
        )
        return
    if not is_mail_fully_configured(app):
        log.warning("Stock crítico %s / %s: SMTP no configurado", categoria, producto)
        return

    cat_label = _categoria_label(categoria)
    faltante = max(stock_minimo - stock_actual, 0.0)
    prod_esc = html_lib.escape(producto)
    asunto = f"QDV — Stock crítico · {producto}"
    cuerpo_html = (
        f"<p>El producto <strong>{prod_esc}</strong> ({html_lib.escape(cat_label)}) "
        f"pasó a <strong style=\"color:#b02a37\">estado crítico</strong>: stock por debajo del mínimo configurado.</p>"
        f"<ul>"
        f"<li><strong>Stock actual:</strong> {stock_actual:.2f}</li>"
        f"<li><strong>Mínimo de alerta:</strong> {stock_minimo:.2f}</li>"
        f"<li><strong>Faltante:</strong> {faltante:.2f}</li>"
        f"</ul>"
        f"<p class=\"text-muted\">Aviso automático al cruzar el umbral. Se reenviará si el stock se recupera y vuelve a caer por debajo del mínimo.</p>"
    )
    cuerpo_texto = (
        f"Stock crítico — {producto} ({cat_label})\n"
        f"Stock actual: {stock_actual:.2f}\n"
        f"Mínimo de alerta: {stock_minimo:.2f}\n"
        f"Faltante: {faltante:.2f}"
    )
    enviar_mail(
        app,
        destinatarios=recipients,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
    )


def maybe_notify_critical_transition(app: Any, categoria: str, producto: str) -> bool:
    """
    Si el producto está en estado crítico y aún no se avisó en este episodio, envía correo.
    Si dejó de estar crítico, limpia el registro para permitir un nuevo aviso en el futuro.

    Returns:
        True si se envió un correo en esta invocación.
    """
    cat = (categoria or "").strip()
    prod = (producto or "").strip()
    if not cat or not prod:
        return False

    minimo = _get_minimo_alerta(cat, prod)
    if minimo is None:
        _clear_sent_if_exists(cat, prod)
        db.session.commit()
        return False

    actual = stock_total_producto(cat, prod)
    nivel = _nivel_alerta_panel(actual, minimo)

    if nivel != "critico":
        if _sent_row(cat, prod) is not None:
            _clear_sent_if_exists(cat, prod)
            db.session.commit()
        return False

    if _sent_row(cat, prod) is not None:
        return False

    try:
        _send_critical_mail(
            app,
            categoria=cat,
            producto=prod,
            stock_actual=actual,
            stock_minimo=minimo,
        )
    except Exception:
        log.exception("Fallo envío mail stock crítico %s / %s", cat, prod)
        return False

    db.session.add(
        StockCriticalAlertSent(
            categoria=cat,
            producto=prod,
            sent_at_iso=now_operacion_local_iso_seconds(),
        )
    )
    db.session.commit()
    return True
