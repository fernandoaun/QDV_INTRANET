from __future__ import annotations

from app.extensions import db


class ProductoTerminado(db.Model):
    """Catálogo de productos terminados para entregas (nombre comercial + vínculo al producto en stock)."""

    __tablename__ = "productos_terminados_entrega"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(256), nullable=False)
    # Nombre exacto del producto en ingresos/consumos (p. ej. «Hipoclorito»).
    stock_producto = db.Column(db.String(256), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)


class ClienteEntrega(db.Model):
    __tablename__ = "clientes_entrega"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(256), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    observaciones = db.Column(db.Text)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)


class LugarEntrega(db.Model):
    __tablename__ = "lugares_entrega"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(512), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes_entrega.id"), nullable=False, index=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)


class ChoferEntrega(db.Model):
    __tablename__ = "choferes_entrega"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(256), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    observaciones = db.Column(db.Text)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)
