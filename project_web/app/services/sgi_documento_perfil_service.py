"""Sectores (perfiles de usuario) a los que aplica cada procedimiento SGI."""
from __future__ import annotations

from app.extensions import db
from app.models.sgi import SgiDocumentoPerfil
from app.models.user import User
from app.user_roles import (
    ROLE_ADMINISTRADOR,
    ROLE_LABORATORISTA,
    ROLE_LABELS,
    ROLE_LOGISTICA,
    ROLE_MANTENIMIENTO,
    ROLE_OPERACIONES,
    ROLE_SGI,
    ROLE_SOLO_LECTURA_TOTAL,
    normalize_stored_rol,
)

# Perfiles seleccionables en el editor (organización operativa + SGI / Angel).
SGI_PERFILES_APLICABLES: tuple[str, ...] = (
    ROLE_OPERACIONES,
    ROLE_LOGISTICA,
    ROLE_MANTENIMIENTO,
    ROLE_SGI,
    ROLE_SOLO_LECTURA_TOTAL,
)

SGI_PERFILES_APLICABLES_LABELS: dict[str, str] = {
    k: ROLE_LABELS[k] for k in SGI_PERFILES_APLICABLES
}

_VALID_PERFILES = frozenset(SGI_PERFILES_APLICABLES) | frozenset({ROLE_ADMINISTRADOR})


def normalize_perfil_keys(raw: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        key = normalize_stored_rol(str(item).strip())
        if key == ROLE_LABORATORISTA:
            continue
        if key not in _VALID_PERFILES or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def perfiles_aplica_documento(documento_id: int) -> list[str]:
    rows = (
        db.session.query(SgiDocumentoPerfil.perfil)
        .filter(SgiDocumentoPerfil.documento_id == int(documento_id))
        .order_by(SgiDocumentoPerfil.perfil)
        .all()
    )
    return [str(r[0]) for r in rows]


def sync_perfiles_documento(documento_id: int, perfiles: list[str] | None) -> list[str]:
    """Reemplaza la lista de perfiles del documento. Devuelve la lista normalizada guardada."""
    doc_id = int(documento_id)
    normalized = normalize_perfil_keys(perfiles)
    existing = {
        str(r.perfil): r
        for r in db.session.query(SgiDocumentoPerfil).filter(SgiDocumentoPerfil.documento_id == doc_id).all()
    }
    for key in normalized:
        if key not in existing:
            db.session.add(SgiDocumentoPerfil(documento_id=doc_id, perfil=key))
    for key, row in existing.items():
        if key not in normalized:
            db.session.delete(row)
    return normalized


def user_perfil_aplica_documento(user: User, documento_id: int) -> bool:
    if user.is_admin:
        return True
    rol = normalize_stored_rol(user.rol)
    return rol in perfiles_aplica_documento(documento_id)


def users_with_perfiles(perfiles: list[str]) -> list[User]:
    """Usuarios activos cuyo perfil está en la lista (sin exigir permiso sgi_hub)."""
    if not perfiles:
        return []
    wanted = set(normalize_perfil_keys(perfiles))
    rows = db.session.query(User).filter(User.activo.is_(True)).order_by(User.id).all()
    out: list[User] = []
    seen: set[int] = set()
    for u in rows:
        if int(u.id) in seen:
            continue
        if u.is_admin:
            continue
        rol = normalize_stored_rol(u.rol)
        if rol == ROLE_LABORATORISTA:
            continue
        if rol in wanted:
            seen.add(int(u.id))
            out.append(u)
    return out
