from __future__ import annotations

from datetime import date, datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlanificacionActividad(db.Model):
    """Actividad planificable (tareas, entregas, mantenimiento, etc.) con soporte futuro para vínculos externos."""

    __tablename__ = "planificacion_actividades"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    codigo = db.Column(db.String(64), nullable=True, unique=True, index=True)
    titulo = db.Column(db.String(256), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    fecha_inicio = db.Column(db.Date, nullable=False, index=True)
    fecha_fin = db.Column(db.Date, nullable=False, index=True)
    duracion_dias = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    responsable_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    categoria = db.Column(db.String(32), nullable=False, default="otro", server_default="otro", index=True)
    prioridad = db.Column(db.String(16), nullable=False, default="media", server_default="media", index=True)
    estado = db.Column(db.String(24), nullable=False, default="pendiente", server_default="pendiente", index=True)
    observaciones = db.Column(db.Text, nullable=True)
    linked_entity_type = db.Column(db.String(32), nullable=True, index=True)
    linked_entity_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    responsable = db.relationship("User", foreign_keys=[responsable_user_id], lazy="joined")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    deps_entrantes = db.relationship(
        "PlanificacionDependencia",
        foreign_keys="PlanificacionDependencia.sucesora_id",
        back_populates="sucesora",
        passive_deletes=True,
    )
    deps_salientes = db.relationship(
        "PlanificacionDependencia",
        foreign_keys="PlanificacionDependencia.predecesora_id",
        back_populates="predecesora",
        passive_deletes=True,
    )

    @staticmethod
    def compute_duracion_dias(fecha_inicio: date, fecha_fin: date) -> int:
        return max(1, (fecha_fin - fecha_inicio).days + 1)


class PlanificacionDependencia(db.Model):
    """
    Dependencia dirigida: la actividad `sucesora` está condicionada por `predecesora`.

    Tipos (PERT/CPM habituales):
    - FS: la sucesora puede arrancar cuando la predecesora terminó.
    - SS: la sucesora arranca cuando arranca la predecesora.
    - FF: la sucesora puede cerrar cuando cierra la predecesora.
    - SF: la sucesora cierra cuando arranca la predecesora.
    """

    __tablename__ = "planificacion_dependencias"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    predecesora_id = db.Column(
        db.Integer,
        db.ForeignKey("planificacion_actividades.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sucesora_id = db.Column(
        db.Integer,
        db.ForeignKey("planificacion_actividades.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo = db.Column(db.String(4), nullable=False, default="FS", server_default="FS")
    lag_dias = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    predecesora = db.relationship(
        "PlanificacionActividad",
        foreign_keys=[predecesora_id],
        back_populates="deps_salientes",
        lazy="joined",
    )
    sucesora = db.relationship(
        "PlanificacionActividad",
        foreign_keys=[sucesora_id],
        back_populates="deps_entrantes",
        lazy="joined",
    )

    __table_args__ = (
        db.UniqueConstraint("predecesora_id", "sucesora_id", name="uq_planificacion_dep_pred_suc"),
    )
