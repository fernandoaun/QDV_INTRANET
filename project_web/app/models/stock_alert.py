from __future__ import annotations

from app.extensions import db


class StockAlertEmail(db.Model):
    """Destinatarios para avisos automáticos de stock crítico (por debajo del mínimo)."""

    __tablename__ = "stock_alert_emails"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(256), nullable=False, unique=True, index=True)


class StockCriticalAlertSent(db.Model):
    """Evita reenviar el mismo aviso mientras el producto sigue en estado crítico."""

    __tablename__ = "stock_critical_alerts_sent"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    categoria = db.Column(db.String(64), nullable=False)
    producto = db.Column(db.String(256), nullable=False)
    sent_at_iso = db.Column(db.String(32), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("categoria", "producto", name="uq_stock_critical_alert_cat_prod"),
    )
