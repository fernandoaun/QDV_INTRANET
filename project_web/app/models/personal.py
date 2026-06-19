from __future__ import annotations

from datetime import date, datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EmpleadoPersonal(db.Model):
    """Legajo RRHH vinculado 1:1 a un User (cuenta del sistema)."""

    __tablename__ = "personal_empleados"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=True, unique=True, index=True
    )
    legajo = db.Column(db.String(32), nullable=False, unique=True, index=True)
    dni = db.Column(db.String(16), nullable=False, default="", server_default="")
    cuil = db.Column(db.String(16), nullable=False, default="", server_default="")
    apellido = db.Column(db.String(128), nullable=False, index=True)
    nombre = db.Column(db.String(128), nullable=False, index=True)
    fecha_nacimiento = db.Column(db.Date, nullable=True, index=True)
    domicilio = db.Column(db.String(256), nullable=False, default="", server_default="")
    telefono = db.Column(db.String(64), nullable=False, default="", server_default="")
    email = db.Column(db.String(256), nullable=False, default="", server_default="")
    puesto = db.Column(db.String(128), nullable=False, default="", server_default="")
    area = db.Column(db.String(128), nullable=False, default="", server_default="")
    fecha_ingreso = db.Column(db.Date, nullable=True)
    estado = db.Column(db.String(16), nullable=False, default="activo", server_default="activo", index=True)
    talle_pantalon = db.Column(db.String(16), nullable=False, default="", server_default="")
    talle_camisa = db.Column(db.String(16), nullable=False, default="", server_default="")
    talle_calzado = db.Column(db.String(16), nullable=False, default="", server_default="")
    talle_guantes = db.Column(db.String(16), nullable=False, default="", server_default="")
    talle_mameluco = db.Column(db.String(16), nullable=False, default="", server_default="")
    observaciones = db.Column(db.String(4000), nullable=False, default="", server_default="")
    operador_id = db.Column(db.Integer, db.ForeignKey("operadores.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("empleado_personal", uselist=False),
    )
    operador = db.relationship("Operador", backref=db.backref("empleado_personal", uselist=False))

    @property
    def nombre_completo(self) -> str:
        return f"{self.apellido}, {self.nombre}".strip(", ")


class PersonalEppItem(db.Model):
    """Catálogo configurable de ítems de ropa y EPP."""

    __tablename__ = "personal_epp_items"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(128), nullable=False, unique=True, index=True)
    categoria = db.Column(db.String(32), nullable=False, default="epp", server_default="epp", index=True)
    requiere_talle = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    entregas = db.relationship("PersonalEntregaEpp", back_populates="item", lazy="dynamic")


class PersonalEntregaEpp(db.Model):
    __tablename__ = "personal_entregas_epp"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    empleado_id = db.Column(
        db.Integer, db.ForeignKey("personal_empleados.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id = db.Column(db.Integer, db.ForeignKey("personal_epp_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    talle = db.Column(db.String(32), nullable=False, default="", server_default="")
    cantidad = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    observaciones = db.Column(db.String(2000), nullable=False, default="", server_default="")
    estado = db.Column(db.String(16), nullable=False, default="pendiente", server_default="pendiente", index=True)
    prenda_anterior_devuelta = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    prenda_anterior_entrega_id = db.Column(
        db.Integer, db.ForeignKey("personal_entregas_epp.id", ondelete="SET NULL"), nullable=True, index=True
    )
    confirmada_at = db.Column(db.DateTime(timezone=True), nullable=True)
    confirmada_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    aviso_pendiente_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    empleado = db.relationship("EmpleadoPersonal", backref=db.backref("entregas_epp", lazy="dynamic"))
    item = db.relationship("PersonalEppItem", back_populates="entregas")
    prenda_anterior_entrega = db.relationship(
        "PersonalEntregaEpp",
        remote_side=[id],
        foreign_keys=[prenda_anterior_entrega_id],
    )
    confirmada_por = db.relationship("User", foreign_keys=[confirmada_by_user_id])


class PersonalCurso(db.Model):
    __tablename__ = "personal_cursos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    empleado_id = db.Column(
        db.Integer, db.ForeignKey("personal_empleados.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre = db.Column(db.String(256), nullable=False)
    institucion = db.Column(db.String(256), nullable=False, default="", server_default="")
    fecha_realizacion = db.Column(db.Date, nullable=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True, index=True)
    observaciones = db.Column(db.String(2000), nullable=False, default="", server_default="")

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    empleado = db.relationship("EmpleadoPersonal", backref=db.backref("cursos", lazy="dynamic"))


class PersonalApercibimiento(db.Model):
    __tablename__ = "personal_apercibimientos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    empleado_id = db.Column(
        db.Integer, db.ForeignKey("personal_empleados.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha = db.Column(db.Date, nullable=False, index=True)
    tipo = db.Column(db.String(16), nullable=False, default="escrito", server_default="escrito")
    motivo = db.Column(db.String(512), nullable=False, default="", server_default="")
    descripcion = db.Column(db.String(4000), nullable=False, default="", server_default="")
    registrado_por = db.Column(db.String(256), nullable=False, default="", server_default="")

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    empleado = db.relationship("EmpleadoPersonal", backref=db.backref("apercibimientos", lazy="dynamic"))


class PersonalArt(db.Model):
    __tablename__ = "personal_art"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    empleado_id = db.Column(
        db.Integer, db.ForeignKey("personal_empleados.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    aseguradora = db.Column(db.String(256), nullable=False, default="", server_default="")
    numero_poliza = db.Column(db.String(64), nullable=False, default="", server_default="")
    fecha_alta = db.Column(db.Date, nullable=True)
    fecha_baja = db.Column(db.Date, nullable=True)
    observaciones = db.Column(db.String(2000), nullable=False, default="", server_default="")

    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    empleado = db.relationship("EmpleadoPersonal", backref=db.backref("art", uselist=False))


class PersonalVacacionPeriodo(db.Model):
    """Días de vacaciones asignados por período (carga del administrador)."""

    __tablename__ = "personal_vacaciones_periodos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    empleado_id = db.Column(
        db.Integer, db.ForeignKey("personal_empleados.id", ondelete="CASCADE"), nullable=False, index=True
    )
    anio = db.Column(db.Integer, nullable=False, index=True)
    dias_asignados = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    observaciones = db.Column(db.String(2000), nullable=False, default="", server_default="")

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    empleado = db.relationship("EmpleadoPersonal", backref=db.backref("vacaciones_periodos", lazy="dynamic"))
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (db.UniqueConstraint("empleado_id", "anio", name="uq_personal_vac_periodo_empleado_anio"),)


class PersonalVacacionConfig(db.Model):
    """Configuración global del módulo de vacaciones (fila única id=1)."""

    __tablename__ = "personal_vacaciones_config"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    responsable_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    responsable = db.relationship("User", foreign_keys=[responsable_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])


class PersonalVacacion(db.Model):
    __tablename__ = "personal_vacaciones"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    empleado_id = db.Column(
        db.Integer, db.ForeignKey("personal_empleados.id", ondelete="CASCADE"), nullable=False, index=True
    )
    periodo_id = db.Column(
        db.Integer, db.ForeignKey("personal_vacaciones_periodos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fecha_desde = db.Column(db.Date, nullable=False, index=True)
    fecha_hasta = db.Column(db.Date, nullable=False, index=True)
    dias = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    anio = db.Column(db.Integer, nullable=False, index=True)
    estado = db.Column(db.String(16), nullable=False, default="solicitada", server_default="solicitada", index=True)
    observaciones = db.Column(db.String(2000), nullable=False, default="", server_default="")
    motivo_responsable = db.Column(db.String(2000), nullable=False, default="", server_default="")
    fecha_desde_original = db.Column(db.Date, nullable=True)
    fecha_hasta_original = db.Column(db.Date, nullable=True)
    solicitada_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    gestionada_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    gestionada_at = db.Column(db.DateTime(timezone=True), nullable=True)
    confirmada_empleado_at = db.Column(db.DateTime(timezone=True), nullable=True)
    solicitud_aviso_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    empleado = db.relationship("EmpleadoPersonal", backref=db.backref("vacaciones", lazy="dynamic"))
    periodo = db.relationship("PersonalVacacionPeriodo", backref=db.backref("solicitudes", lazy="dynamic"))
    solicitada_por = db.relationship("User", foreign_keys=[solicitada_by_user_id])
    gestionada_por = db.relationship("User", foreign_keys=[gestionada_by_user_id])
