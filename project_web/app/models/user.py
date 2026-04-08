from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(128), nullable=False, unique=True, index=True)
    nombre_completo = db.Column(db.String(256), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    # Perfil operativo (ver app.user_roles). Sincronizado con is_admin si rol == administrador.
    rol = db.Column(db.String(32), nullable=False, default="operaciones", server_default="operaciones")
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)

    permisos = db.relationship(
        "PermisoUsuario",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
        foreign_keys="PermisoUsuario.user_id",
    )


class PermisoUsuario(db.Model):
    __tablename__ = "permisos_usuario"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    permiso = db.Column(db.String(64), nullable=False)
    habilitado = db.Column(db.Boolean, nullable=False, default=True)
    puede_editar = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (db.UniqueConstraint("user_id", "permiso", name="uq_permiso_user_perm"),)
