"""Modelos del módulo SGC – Sistema de Gestión de la Calidad.

Estructura preparada para ampliar con: difusión documental, lecturas por usuario,
organigrama, control de cambios, matriz documental, documentos externos y vencimientos.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Tipos de documento SGC (constante TIPO_MSGI conservada por compatibilidad de imports)
TIPO_PG = "PG"
TIPO_PO = "PO"
TIPO_MSGI = "MSGC"
TIPO_MSGC = TIPO_MSGI

TIPOS_DOCUMENTO: tuple[str, ...] = (TIPO_PG, TIPO_PO, TIPO_MSGI)

TIPO_SLUGS: dict[str, str] = {
    TIPO_PG: "pg",
    TIPO_PO: "po",
    TIPO_MSGI: "msgc",
}

SLUG_TO_TIPO: dict[str, str] = {v: k for k, v in TIPO_SLUGS.items()}
# Alias legado (bookmarks / enlaces antiguos)
SLUG_TO_TIPO["msgi"] = TIPO_MSGI

TIPO_LABELS: dict[str, str] = {
    TIPO_PG: "PG – Procedimientos de Gestión",
    TIPO_PO: "PO – Procedimientos Operativos",
    TIPO_MSGI: "MSGC – Manual del sistema de gestión de la calidad",
}

TIPO_CARATULA_LABELS: dict[str, str] = {
    TIPO_PG: "PROCEDIMIENTO DE GESTIÓN",
    TIPO_PO: "PROCEDIMIENTO OPERATIVO",
    TIPO_MSGI: "MANUAL DEL SISTEMA DE GESTIÓN DE LA CALIDAD",
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

TIPOS_PROCEDIMIENTO_VISUAL: tuple[str, ...] = (TIPO_PG, TIPO_PO, TIPO_MSGI)

ANEXO_TIPO_ARCHIVO = "archivo"
ANEXO_TIPO_DOCUMENTO = "documento"
ANEXO_TIPO_ORGANIGRAMA = "organigrama"

ANEXO_TIPOS_CONTENIDO: tuple[str, ...] = (
    ANEXO_TIPO_ARCHIVO,
    ANEXO_TIPO_DOCUMENTO,
    ANEXO_TIPO_ORGANIGRAMA,
)


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
    tipo_contenido = db.Column(db.String(32), nullable=True)
    fecha_aprobacion = db.Column(db.Date, nullable=True, index=True)

    codigo_archivado = db.Column(db.String(64), nullable=True)
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])
    deleted_by = db.relationship("User", foreign_keys=[deleted_by_id])

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

    documento = db.relationship(
        "SgiDocumento",
        backref=db.backref(
            "historial",
            lazy="dynamic",
            order_by="SgiDocumentoHistorial.fecha.desc()",
            cascade="all, delete-orphan",
        ),
    )


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
            cascade="all, delete-orphan",
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


# Orígenes / tipos de asociación de registros digitales (punto 7).
ASSOC_EXISTING_MODULE = "existing_module"
ASSOC_IMPORTED_WORD = "imported_word"
ASSOC_IMPORTED_EXCEL = "imported_excel"
ASSOC_MANUAL_FORM = "manual_form"

ASSOC_TYPES: tuple[str, ...] = (
    ASSOC_EXISTING_MODULE,
    ASSOC_IMPORTED_WORD,
    ASSOC_IMPORTED_EXCEL,
    ASSOC_MANUAL_FORM,
)

RECORD_STATUS_ACTIVE = "activo"
RECORD_STATUS_DRAFT = "borrador"
RECORD_STATUS_INACTIVE = "inactivo"

ENTRY_STATUS_DRAFT = "borrador"
ENTRY_STATUS_SUBMITTED = "enviado"
ENTRY_STATUS_CLOSED = "cerrado"

RECORD_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
RECORD_ALLOWED_EXTENSIONS: tuple[str, ...] = (".docx", ".xlsx", ".xls")


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
    modulo = db.Column(db.String(64), nullable=False, default="", server_default="")
    association_type = db.Column(db.String(32), nullable=False, default="", server_default="")
    record_definition_id = db.Column(
        db.Integer,
        db.ForeignKey("sgi_record_definitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    record_definition = db.relationship(
        "SgiRecordDefinition",
        foreign_keys=[record_definition_id],
        backref=db.backref("procedure_registros", lazy="dynamic"),
    )


class SgiRecordFile(db.Model):
    """Archivo fuente (Word/Excel) de un registro digital parametrizado."""

    __tablename__ = "sgi_record_files"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    original_name = db.Column(db.String(512), nullable=False, default="", server_default="")
    safe_name = db.Column(db.String(512), nullable=False, default="", server_default="")
    extension = db.Column(db.String(16), nullable=False, default="", server_default="")
    mime_type = db.Column(db.String(128), nullable=False, default="", server_default="")
    size_bytes = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    content_hash = db.Column(db.String(128), nullable=False, default="", server_default="", index=True)
    storage_path = db.Column(db.String(1024), nullable=False, default="", server_default="")
    analysis_status = db.Column(db.String(32), nullable=False, default="pending", server_default="pending")
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])


class SgiRecordDefinition(db.Model):
    """Definición de un registro digital editable (no el archivo Office)."""

    __tablename__ = "sgi_record_definitions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code = db.Column(db.String(64), nullable=False, default="", server_default="", index=True)
    name = db.Column(db.String(512), nullable=False, default="", server_default="")
    description = db.Column(db.String(4000), nullable=False, default="", server_default="")
    origin_type = db.Column(db.String(32), nullable=False, default="", server_default="", index=True)
    source_file_id = db.Column(
        db.Integer, db.ForeignKey("sgi_record_files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status = db.Column(db.String(32), nullable=False, default=RECORD_STATUS_ACTIVE, server_default=RECORD_STATUS_ACTIVE, index=True)
    current_version_id = db.Column(db.Integer, nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)

    source_file = db.relationship("SgiRecordFile", foreign_keys=[source_file_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])
    versions = db.relationship(
        "SgiRecordDefinitionVersion",
        back_populates="definition",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="SgiRecordDefinitionVersion.version_number",
    )


class SgiRecordDefinitionVersion(db.Model):
    __tablename__ = "sgi_record_definition_versions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    record_definition_id = db.Column(
        db.Integer, db.ForeignKey("sgi_record_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    schema_json = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    ui_schema_json = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    change_description = db.Column(db.String(2000), nullable=False, default="", server_default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    definition = db.relationship("SgiRecordDefinition", back_populates="versions", foreign_keys=[record_definition_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        db.UniqueConstraint("record_definition_id", "version_number", name="uq_sgi_record_def_version"),
    )


class SgiRecordEntry(db.Model):
    """Carga (instancia) de un registro digital."""

    __tablename__ = "sgi_record_entries"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    record_definition_id = db.Column(
        db.Integer, db.ForeignKey("sgi_record_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    record_definition_version_id = db.Column(
        db.Integer,
        db.ForeignKey("sgi_record_definition_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entry_number = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    status = db.Column(db.String(32), nullable=False, default=ENTRY_STATUS_DRAFT, server_default=ENTRY_STATUS_DRAFT, index=True)
    data_json = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    definition = db.relationship("SgiRecordDefinition", foreign_keys=[record_definition_id])
    version = db.relationship("SgiRecordDefinitionVersion", foreign_keys=[record_definition_version_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])


class SgiRecordAuditLog(db.Model):
    __tablename__ = "sgi_record_audit_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    entity_type = db.Column(db.String(64), nullable=False, default="", server_default="", index=True)
    entity_id = db.Column(db.Integer, nullable=False, default=0, server_default="0", index=True)
    action = db.Column(db.String(64), nullable=False, default="", server_default="", index=True)
    previous_data = db.Column(db.Text, nullable=True)
    new_data = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    user = db.relationship("User", foreign_keys=[user_id])


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
    tipo_contenido = db.Column(db.String(32), nullable=False, default=ANEXO_TIPO_ARCHIVO, server_default=ANEXO_TIPO_ARCHIVO)
    contenido_json = db.Column(db.Text, nullable=False, default="{}", server_default="{}")


class SgiNotificacion(db.Model):
    """Avisos in-app (campana) para usuarios del módulo SGC."""

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
