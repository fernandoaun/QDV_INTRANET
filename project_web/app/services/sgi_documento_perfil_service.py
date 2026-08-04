"""Puestos (organigrama) / perfiles a los que aplica cada procedimiento SGI."""
from __future__ import annotations

from app.extensions import db
from app.models.sgi import SgiDocumentoPerfil
from app.models.user import User
from app.user_roles import (
    ROLE_ADMINISTRADOR,
    ROLE_ADMINISTRACION,
    ROLE_LABORATORISTA,
    ROLE_LABELS,
    ROLE_LOGISTICA,
    ROLE_MANTENIMIENTO,
    ROLE_MANTENIMIENTO_OPERACIONES,
    ROLE_OPERACIONES,
    ROLE_SGI,
    ROLE_SOLO_LECTURA_TOTAL,
    normalize_stored_rol,
    role_covers_perfiles,
)

# Roles legacy (sigue aceptándose en sync/notificación para docs viejos y cobertura por perfil).
SGI_PERFILES_APLICABLES: tuple[str, ...] = (
    ROLE_OPERACIONES,
    ROLE_LOGISTICA,
    ROLE_ADMINISTRACION,
    ROLE_MANTENIMIENTO,
    ROLE_MANTENIMIENTO_OPERACIONES,
    ROLE_SGI,
    ROLE_SOLO_LECTURA_TOTAL,
)

SGI_PERFILES_APLICABLES_LABELS: dict[str, str] = {
    k: ROLE_LABELS[k] for k in SGI_PERFILES_APLICABLES
}

_VALID_ROLES = frozenset(SGI_PERFILES_APLICABLES) | frozenset({ROLE_ADMINISTRADOR})


def _organigrama_puesto_opciones() -> list[dict[str, str]]:
    from app.services import sgi_anexo_service as anexo_svc

    return anexo_svc.organigrama_puesto_opciones()


def _organigrama_rol_by_node_id() -> dict[str, str]:
    from app.services.sgi_anexo_service import ORGANIGRAMA_QDV_SPECS

    out: dict[str, str] = {}
    for spec in ORGANIGRAMA_QDV_SPECS:
        nid = str(spec.get("id") or "")
        rol = normalize_stored_rol(spec.get("rol")) if spec.get("rol") else ""
        if nid and rol and rol != ROLE_LABORATORISTA:
            out[nid] = rol
    return out


def perfiles_opciones_documento() -> dict[str, str]:
    """Opciones del editor: puestos del organigrama (id → título)."""
    return {p["id"]: p["titulo"] for p in _organigrama_puesto_opciones()}


def _node_ids_for_role(role_key: str) -> list[str]:
    role = normalize_stored_rol(role_key)
    if not role or role not in _VALID_ROLES:
        return []
    return [nid for nid, rol in _organigrama_rol_by_node_id().items() if rol == role]


def expand_keys_for_ui(keys: list[str] | None) -> list[str]:
    """Marca checkboxes: expande roles legacy a puestos del organigrama."""
    valid_nodes = set(perfiles_opciones_documento().keys())
    out: list[str] = []
    seen: set[str] = set()
    for item in keys or []:
        key = str(item).strip()
        if not key:
            continue
        role = normalize_stored_rol(key)
        if key in valid_nodes:
            if key not in seen:
                seen.add(key)
                out.append(key)
            continue
        if role in _VALID_ROLES:
            for nid in _node_ids_for_role(role):
                if nid not in seen:
                    seen.add(nid)
                    out.append(nid)
            # Roles sin nodo (p. ej. Angel / combinados) se conservan si no hay expansión.
            if not _node_ids_for_role(role) and role not in seen and role != ROLE_LABORATORISTA:
                seen.add(role)
                out.append(role)
    return out


def normalize_perfil_keys(raw: list[str] | None) -> list[str]:
    """Acepta ids de puesto del organigrama y roles legacy; deduplica."""
    valid_nodes = set(perfiles_opciones_documento().keys())
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        key = str(item).strip()
        if not key or key in seen:
            continue
        role = normalize_stored_rol(key)
        if key in valid_nodes:
            seen.add(key)
            out.append(key)
            continue
        if role == ROLE_LABORATORISTA:
            continue
        if role in _VALID_ROLES:
            seen.add(role)
            out.append(role)
    return out


def perfiles_aplica_documento(documento_id: int) -> list[str]:
    rows = (
        db.session.query(SgiDocumentoPerfil.perfil)
        .filter(SgiDocumentoPerfil.documento_id == int(documento_id))
        .order_by(SgiDocumentoPerfil.perfil)
        .all()
    )
    return [str(r[0]) for r in rows]


def perfiles_aplica_para_editor(documento_id: int) -> list[str]:
    """Claves para checkboxes del editor (incluye expansión de roles legacy)."""
    return expand_keys_for_ui(perfiles_aplica_documento(documento_id))


def sync_perfiles_documento(documento_id: int, perfiles: list[str] | None) -> list[str]:
    """Reemplaza la lista de puestos/perfiles del documento. Devuelve la lista normalizada guardada."""
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


def _wanted_roles_and_nodes(keys: list[str]) -> tuple[set[str], set[str]]:
    """Separa roles a cubrir y nodos de organigrama seleccionados."""
    valid_nodes = set(perfiles_opciones_documento().keys())
    roles: set[str] = set()
    nodes: set[str] = set()
    rol_by_node = _organigrama_rol_by_node_id()
    for key in normalize_perfil_keys(keys):
        if key in valid_nodes:
            nodes.add(key)
            mapped = rol_by_node.get(key)
            if mapped:
                roles.add(mapped)
            continue
        role = normalize_stored_rol(key)
        if role in _VALID_ROLES:
            roles.add(role)
    return roles, nodes


def user_perfil_aplica_documento(user: User, documento_id: int) -> bool:
    if user.is_admin:
        return True
    roles, nodes = _wanted_roles_and_nodes(perfiles_aplica_documento(documento_id))
    if not roles and not nodes:
        return False
    from app.services import sgi_anexo_service as anexo_svc

    if nodes and set(anexo_svc.organigrama_node_ids_for_user(int(user.id))) & nodes:
        return True
    covered = role_covers_perfiles(user.rol)
    return bool(covered & roles)


def users_with_perfiles(perfiles: list[str]) -> list[User]:
    """Usuarios activos: titulares de puestos seleccionados y/o perfiles/roles asociados."""
    roles, nodes = _wanted_roles_and_nodes(perfiles)
    if not roles and not nodes:
        return []

    holder_ids: set[int] = set()
    if nodes:
        from app.services import sgi_anexo_service as anexo_svc

        for nid in nodes:
            for holder in anexo_svc.organigrama_puesto_holders(nid):
                try:
                    holder_ids.add(int(holder["user_id"]))
                except (KeyError, TypeError, ValueError):
                    continue

    rows = db.session.query(User).filter(User.activo.is_(True)).order_by(User.id).all()
    out: list[User] = []
    seen: set[int] = set()
    for u in rows:
        uid = int(u.id)
        if uid in seen:
            continue
        if u.is_admin:
            continue
        rol = normalize_stored_rol(u.rol)
        if rol == ROLE_LABORATORISTA:
            continue
        by_role = bool(roles and (role_covers_perfiles(rol) & roles))
        by_node = uid in holder_ids
        if by_role or by_node:
            seen.add(uid)
            out.append(u)
    return out
