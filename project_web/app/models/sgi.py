"""Modelos del módulo SGI – Sistema de Gestión Integrado.

Estructura preparada para ampliar con: difusión documental, lecturas por usuario,
organigrama, control de cambios, matriz documental, documentos externos y vencimientos.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Tipos de documento SGI
TIPO_PG = "PG"
TIPO_PO = "PO"
TIPO_MSGI = "MSGI"

TIPOS_DOCUMENTO: tuple[str, ...] = (TIPO_PG, TIPO_PO, TIPO_MSGI)

TIPO_SLUGS: dict[str, str] = {
    TIPO_PG: "pg",
    TIPO_PO: "po",
    TIPO_MSGI: "msgi",
}

SLUG_TO_TIPO: dict[str, str] = {v: k for k, v in TIPO_SLUGS.items()}

TIPO_LABELS: dict[str, str] = {
    TIPO_PG: "PG – Procedimientos de Gestión",
    TIPO_PO: "PO – Procedimientos Operativos",
    TIPO_MSGI: "MSGI – Manual del Sistema de Gestión Integrado",
}

TIPO_CARATULA_LABELS: dict[str, str] = {
    TIPO_PG: "PROCEDIMIENTO DE GESTIÓN",
    TIPO_PO: "PROCEDIMIENTO OPERATIVO",
    TIPO_MSGI: "MANUAL DEL SISTEMA DE GESTIÓN INTEGRADO",
}

ESTADO_BORRADOR = "borrador"
ESTADO_EN_REVISION = "en_revision"
ESTADO_REVISADO = "revisado"
ESTADO_APROBADO = "aprobado"
ESTADO_VIGENTE = "vigente"
ESTADO_OBSOLETO = "obsoleto"

ESTADOS_DOCUMENTO: tuple[str, ...] = (
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADO_REVISADO,
    ESTADO_APROBADO,
    ESTADO_VIGENTE,
    ESTADO_OBSOLETO,
)

ESTADOS_PROCEDIMIENTO_WORKFLOW: tuple[str, ...] = (
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADO_REVISADO,
    ESTADO_APROBADO,
    ESTADO_OBSOLETO,
)

ESTADO_LABELS: dict[str, str] = {
    ESTADO_BORRADOR: "Borrador",
    ESTADO_EN_REVISION: "En revisión",
    ESTADO_REVISADO: "Revisado — pendiente de aprobación",
    ESTADO_APROBADO: "Aprobado",
    ESTADO_VIGENTE: "Vigente",
    ESTADO_OBSOLETO: "Obsoleto",
}

# Apartados estándar del cuerpo (formato QDV-PG-01)
PROCEDIMIENTO_SECCIONES: tuple[tuple[str, str], ...] = (
    ("objeto", "1.- OBJETO"),
    ("alcance", "2.- ALCANCE"),
    ("definiciones", "3.- DEFINICIONES"),
    ("responsabilidades", "4.- RESPONSABILIDADES"),
    ("desarrollo", "5.- DESARROLLO"),
    ("referencias", "6.- REFERENCIAS"),
    ("control_registros", "7.- CONTROL DE REGISTROS"),
    ("anexos", "8.- ANEXOS"),
)

TIPOS_PROCEDIMIENTO_VISUAL: tuple[str, ...] = (TIPO_PG, TIPO_PO)


class SgiDocumento(db.Model):
    __tablename__ = "sgi_documentos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tipo = db.Column(db.String(8), nullable=False, index=True)
    codigo = db.Column(db.String(64), nullable=False, index=True)
    titulo = db.Column(db.String(512), nullable=False, index=True)
    revision = db.Column(db.String(32), nullable=False, default="", server_default="")
    fecha_creacion_doc = db.Column(db.Date, nullable=True, index=True)
    fecha_ultima_revision = db.Column(db.Date, nullable=True, index=True)
    responsable_elaboracion = db.Column(db.String(256), nullable=False, default="", server_default="")
    responsable_revision = db.Column(db.String(256), nullable=False, default="", server_default="")
    responsable_aprobacion = db.Column(db.String(256), nullable=False, default="", server_default="")
    estado = db.Column(db.String(32), nullable=False, default=ESTADO_BORRADOR, server_default=ESTADO_BORRADOR, index=True)
    observaciones = db.Column(db.String(8000), nullable=False, default="", server_default="")
    archivo_path = db.Column(db.String(512), nullable=True)
    es_procedimiento_visual = db.Column(db.Boolean, nullable=False, default=False)
    fecha_aprobacion = db.Column(db.Date, nullable=True, index=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])

    perfiles_aplica = db.relationship(
        "SgiDocumentoPerfil",
        backref="documento",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint("tipo", "codigo", name="uq_sgi_documentos_tipo_codigo"),
    )


class SgiDocumentoPerfil(db.Model):
    """Perfiles (sectores) de la organización a los que aplica un procedimiento."""

    __tablename__ = "sgi_documento_perfiles"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    documento_id = db.Column(
        db.Integer, db.ForeignKey("sgi_documentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    perfil = db.Column(db.String(32), nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint("documento_id", "perfil", name="uq_sgi_documento_perfil"),
    )


class SgiDocumentoHistorial(db.Model):
    __tablename__ = "sgi_documentos_historial"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    documento_id = db.Column(
        db.Integer, db.ForeignKey("sgi_documentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    usuario = db.Column(db.String(256), nullable=False, default="", server_default="")
    accion = db.Column(db.String(64), nullable=False, index=True)
    detalle = db.Column(db.String(8000), nullable=False, default="", server_default="")

    documento = db.relationship("SgiDocumento", backref=db.backref("historial", lazy="dynamic", order_by="SgiDocumentoHistorial.fecha.desc()"))


class SgiProcedimientoRevision(db.Model):
    __tablename__ = "sgi_procedimiento_revisiones"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    documento_id = db.Column(
        db.Integer, db.ForeignKey("sgi_documentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero_revision = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    revision_label = db.Column(db.String(32), nullable=False, default="Rev. 00", server_default="Rev. 00")
    estado = db.Column(db.String(32), nullable=False, default=ESTADO_BORRADOR, server_default=ESTADO_BORRADOR, index=True)
    contenido_json = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    fecha_vigencia = db.Column(db.Date, nullable=True)
    elaboro = db.Column(db.String(256), nullable=False, default="", server_default="")
    reviso = db.Column(db.String(256), nullable=False, default="", server_default="")
    revisor_correo = db.Column(db.String(256), nullable=False, default="", server_default="")
    aprobo = db.Column(db.String(256), nullable=False, default="", server_default="")
    aprobador_correo = db.Column(db.String(256), nullable=False, default="", server_default="")
    fecha_elaboracion = db.Column(db.Date, nullable=True)
    fecha_revision = db.Column(db.Date, nullable=True)
    fecha_aprobacion = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    documento = db.relationship(
        "SgiDocumento",
        backref=db.backref(
            "revisiones_proc",
            lazy="dynamic",
            order_by="SgiProcedimientoRevision.numero_revision.desc()",
        ),
    )
    control_cambios = db.relationship(
        "SgiProcedimientoControlCambio",
        backref="proc_revision",
        lazy="dynamic",
        order_by="SgiProcedimientoControlCambio.orden",
        cascade="all, delete-orphan",
    )
    registros = db.relationship(
        "SgiProcedimientoRegistro",
        backref="proc_revision",
        lazy="dynamic",
        order_by="SgiProcedimientoRegistro.orden",
        cascade="all, delete-orphan",
    )
    anexos = db.relationship(
        "SgiProcedimientoAnexo",
        backref="proc_revision",
        lazy="dynamic",
        order_by="SgiProcedimientoAnexo.orden",
        cascade="all, delete-orphan",
    )
    aprobaciones = db.relationship(
        "SgiProcedimientoAprobacion",
        backref="proc_revision",
        lazy="dynamic",
        order_by="SgiProcedimientoAprobacion.fecha.desc()",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint("documento_id", "numero_revision", name="uq_sgi_proc_rev_doc_num"),
    )


class SgiProcedimientoControlCambio(db.Model):
    __tablename__ = "sgi_procedimiento_control_cambios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    revision_id = db.Column(
        db.Integer, db.ForeignKey("sgi_procedimiento_revisiones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    revision_ref = db.Column(db.String(32), nullable=False, default="", server_default="")
    descripcion = db.Column(db.String(4000), nullable=False, default="", server_default="")
    fecha_aprobacion = db.Column(db.Date, nullable=True)


class SgiProcedimientoRegistro(db.Model):
    __tablename__ = "sgi_procedimiento_registros"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    revision_id = db.Column(
        db.Integer, db.ForeignKey("sgi_procedimiento_revisiones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    nombre = db.Column(db.String(512), nullable=False, default="", server_default="")
    quien_archiva = db.Column(db.String(512), nullable=False, default="", server_default="")
    como = db.Column(db.String(512), nullable=False, default="", server_default="")
    donde = db.Column(db.String(512), nullable=False, default="", server_default="")
    tiempo_guarda = db.Column(db.String(256), nullable=False, default="", server_default="")
    usuarios = db.Column(db.String(512), nullable=False, default="", server_default="")
    disposicion_final = db.Column(db.String(512), nullable=False, default="", server_default="")


class SgiProcedimientoAnexo(db.Model):
    __tablename__ = "sgi_procedimiento_anexos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    revision_id = db.Column(
        db.Integer, db.ForeignKey("sgi_procedimiento_revisiones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orden = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    nombre = db.Column(db.String(512), nullable=False, default="", server_default="")
    codigo = db.Column(db.String(64), nullable=False, default="", server_default="")
    revision = db.Column(db.String(32), nullable=False, default="", server_default="")
    fecha_vigencia = db.Column(db.Date, nullable=True)
    archivo_path = db.Column(db.String(512), nullable=True)


class SgiNotificacion(db.Model):
    """Avisos in-app (campana) para usuarios del módulo SGI."""

    __tablename__ = "sgi_notificaciones"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    documento_id = db.Column(
        db.Integer, db.ForeignKey("sgi_documentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_id = db.Column(
        db.Integer, db.ForeignKey("sgi_procedimiento_revisiones.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mensaje = db.Column(db.String(512), nullable=False, default="", server_default="")
    enlace = db.Column(db.String(512), nullable=False, default="", server_default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    usuario = db.relationship("User", foreign_keys=[user_id])
    documento = db.relationship("SgiDocumento", foreign_keys=[documento_id])


class SgiProcedimientoAprobacion(db.Model):
    __tablename__ = "sgi_procedimiento_aprobaciones"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    revision_id = db.Column(
        db.Integer, db.ForeignKey("sgi_procedimiento_revisiones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    accion = db.Column(db.String(64), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    usuario_label = db.Column(db.String(256), nullable=False, default="", server_default="")
    fecha = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    detalle = db.Column(db.String(4000), nullable=False, default="", server_default="")
