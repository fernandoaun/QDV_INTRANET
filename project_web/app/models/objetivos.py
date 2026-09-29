from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ObjetivoPrograma(db.Model):
    """Programa de Objetivos anual (registro SGI QDV-RG-PG-02_01)."""

    __tablename__ = "objetivos_programas"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    anio = db.Column(db.Integer, nullable=False, unique=True, index=True)
    codigo = db.Column(db.String(64), nullable=False, default="QDV-RG-PG-02_01", server_default="QDV-RG-PG-02_01")
    revision = db.Column(db.String(16), nullable=False, default="00", server_default="00")
    fecha_vigencia = db.Column(db.Date, nullable=True)
    fecha_actualizacion = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    objetivos = db.relationship(
        "Objetivo",
        back_populates="programa",
        order_by="Objetivo.orden",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Objetivo(db.Model):
    """Fila del programa: proceso, objetivo, meta, indicador y seguimiento."""

    __tablename__ = "objetivos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    programa_id = db.Column(
        db.Integer, db.ForeignKey("objetivos_programas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    proceso = db.Column(db.String(128), nullable=False, default="", server_default="")
    objetivo = db.Column(db.Text, nullable=False, default="", server_default="")
    meta = db.Column(db.String(256), nullable=False, default="", server_default="")
    indicador = db.Column(db.String(256), nullable=False, default="", server_default="")
    estado_cumplimiento = db.Column(db.String(24), nullable=True)
    recursos = db.Column(db.Text, nullable=False, default="", server_default="")
    frecuencia = db.Column(db.String(64), nullable=False, default="Mensual", server_default="Mensual")
    # Baja lógica: el objetivo deja de mostrarse pero se conserva su historial.
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    programa = db.relationship("ObjetivoPrograma", back_populates="objetivos")
    meses = db.relationship(
        "ObjetivoMes",
        back_populates="objetivo_rel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class ObjetivoMes(db.Model):
    """Seguimiento de un mes (1–12) o del total anual (13): color de estado y valor del indicador."""

    __tablename__ = "objetivos_meses"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    objetivo_id = db.Column(db.Integer, db.ForeignKey("objetivos.id", ondelete="CASCADE"), nullable=False, index=True)
    mes = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(24), nullable=True)
    valor = db.Column(db.String(64), nullable=False, default="", server_default="")

    objetivo_rel = db.relationship("Objetivo", back_populates="meses")

    __table_args__ = (db.UniqueConstraint("objetivo_id", "mes", name="uq_objetivos_meses_obj_mes"),)


class ObjetivoCambio(db.Model):
    """Quién cambió qué en el programa y cuándo."""

    __tablename__ = "objetivos_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    programa_id = db.Column(
        db.Integer, db.ForeignKey("objetivos_programas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    objetivo_id = db.Column(db.Integer, db.ForeignKey("objetivos.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    campo = db.Column(db.String(64), nullable=False)
    antes = db.Column(db.Text, nullable=True)
    despues = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", lazy="joined")
    objetivo_rel = db.relationship("Objetivo", lazy="joined")
