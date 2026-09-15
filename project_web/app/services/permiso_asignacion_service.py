"""Asignación de recursos ACL por puesto (organigrama) y detección de claves nuevas."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.constants import PERMISSION_FORM_KEYS, PERMISSION_KEYS, PERMISSION_LABELS
from app.extensions import db
from app.models import PermisoPuesto, PermisoRecursoConocido, PermisoUsuario, User
from app.user_roles import (
    ROLE_ADMINISTRADOR,
    ROLE_LABORATORISTA,
    ROLE_SGI,
    ROLE_SOLO_LECTURA_TOTAL,
    compute_session_perm_lists,
    merge_puesto_into_role_template,
    normalize_stored_rol,
    role_template_perm_sets,
)

_FIXED_TEMPLATE_ROLES = frozenset(
    {ROLE_ADMINISTRADOR, ROLE_LABORATORISTA, ROLE_SOLO_LECTURA_TOTAL, ROLE_SGI}
)

# Recursos compartidos por todos los puestos (y por quienes no tienen puesto).
PUESTO_COMUN_ID = "__comun__"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def permission_label(key: str) -> str:
    return PERMISSION_LABELS.get(key, key)


def user_uses_fixed_perm_template(user: User | None) -> bool:
    if user is None:
        return True
    if bool(getattr(user, "is_admin", False)):
        return True
    return normalize_stored_rol(getattr(user, "rol", None)) in _FIXED_TEMPLATE_ROLES


def perm_flags_from_form(form) -> dict[str, tuple[bool, bool]]:
    """Lee checkboxes permv_* / perme_* del formulario admin."""
    out: dict[str, tuple[bool, bool]] = {}
    for key in PERMISSION_FORM_KEYS:
        if key not in PERMISSION_KEYS:
            continue
        fv = form.get(f"permv_{key}") == "1"
        fe = form.get(f"perme_{key}") == "1"
        if fe and not fv:
            fe = False
        out[key] = (fv, fe)
    return out


def ensure_schema() -> None:
    """Crea tablas locales si Alembic no corrió y marca el catálogo actual como conocido."""
    try:
        PermisoPuesto.__table__.create(bind=db.engine, checkfirst=True)
        PermisoRecursoConocido.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()
        return
    seed_known_permission_keys_if_empty()


def seed_known_permission_keys_if_empty() -> None:
    """Si no hay baseline, el catálogo vigente no se trata como 'nuevo'."""
    try:
        n = db.session.scalar(select(func.count()).select_from(PermisoRecursoConocido)) or 0
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        return
    if int(n) > 0:
        return
    now = _utc_now()
    for key in PERMISSION_KEYS:
        db.session.add(PermisoRecursoConocido(permiso=key, reconocido_at=now))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def mark_permission_keys_known(keys: list[str] | set[str]) -> None:
    wanted = {str(k).strip() for k in keys if str(k).strip() in PERMISSION_KEYS}
    if not wanted:
        return
    try:
        existing = set(
            db.session.scalars(
                select(PermisoRecursoConocido.permiso).where(PermisoRecursoConocido.permiso.in_(wanted))
            ).all()
        )
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        return
    now = _utc_now()
    for key in wanted - existing:
        db.session.add(PermisoRecursoConocido(permiso=key, reconocido_at=now))


def acknowledge_new_permission_keys() -> int:
    """Marca todos los recursos actuales como vistos (oculta el aviso)."""
    pending = [row["key"] for row in new_unassigned_resources()]
    mark_permission_keys_known(pending)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return 0
    return len(pending)


def _known_permission_keys() -> set[str]:
    try:
        rows = db.session.scalars(select(PermisoRecursoConocido.permiso)).all()
        return {str(k) for k in rows if k}
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        return set(PERMISSION_KEYS)


def new_unassigned_resources() -> list[dict[str, str]]:
    """Claves del código que aún no fueron asignadas ni reconocidas."""
    known = _known_permission_keys()
    out: list[dict[str, str]] = []
    for key in PERMISSION_KEYS:
        if key not in known:
            out.append({"key": key, "label": permission_label(key)})
    return out


def _perm_sets_for_ids(ids: set[str]) -> tuple[set[str], set[str]]:
    if not ids:
        return set(), set()
    try:
        rows = list(
            db.session.scalars(select(PermisoPuesto).where(PermisoPuesto.puesto_id.in_(ids))).all()
        )
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        return set(), set()
    view: set[str] = set()
    edit: set[str] = set()
    for r in rows:
        p = (r.permiso or "").strip()
        if p not in PERMISSION_KEYS:
            continue
        if not r.habilitado:
            continue
        view.add(p)
        if bool(getattr(r, "puede_editar", True)):
            edit.add(p)
    edit &= view
    return view, edit


def comunes_perm_sets() -> tuple[set[str], set[str]]:
    return _perm_sets_for_ids({PUESTO_COMUN_ID})


def is_puesto_comun(puesto_id: str | None) -> bool:
    return (puesto_id or "").strip() == PUESTO_COMUN_ID


def view_edit_for_puestos(puesto_ids: list[str] | set[str] | None) -> tuple[set[str], set[str]]:
    """Unión de recursos comunes + los de los puestos indicados."""
    ids = {
        str(x).strip()
        for x in (puesto_ids or [])
        if str(x).strip() and str(x).strip() != PUESTO_COMUN_ID
    }
    cv, ce = comunes_perm_sets()
    pv, pe = _perm_sets_for_ids(ids)
    view = cv | pv
    edit = (ce | pe) & view
    return view, edit


def puesto_own_perm_sets(puesto_id: str) -> tuple[set[str], set[str]]:
    """Solo lo guardado en ese puesto, sin sumar comunes."""
    nid = (puesto_id or "").strip()
    if not nid:
        return set(), set()
    return _perm_sets_for_ids({nid})


def puesto_perm_sets(puesto_id: str) -> tuple[set[str], set[str]]:
    if is_puesto_comun(puesto_id):
        return comunes_perm_sets()
    return view_edit_for_puestos([puesto_id])


def puesto_assigned_counts() -> dict[str, int]:
    """Cantidad de recursos habilitados por puesto_id."""
    try:
        rows = db.session.execute(
            select(PermisoPuesto.puesto_id, func.count())
            .where(PermisoPuesto.habilitado.is_(True))
            .group_by(PermisoPuesto.puesto_id)
        ).all()
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        return {}
    return {str(pid): int(n or 0) for pid, n in rows}


def replace_puesto_permissions(puesto_id: str, flags: dict[str, tuple[bool, bool]]) -> None:
    nid = (puesto_id or "").strip()
    if not nid:
        return
    cv, ce = (set(), set())
    if nid != PUESTO_COMUN_ID:
        cv, ce = comunes_perm_sets()
    db.session.execute(delete(PermisoPuesto).where(PermisoPuesto.puesto_id == nid))
    granted: list[str] = []
    for key, (fv, fe) in flags.items():
        if key not in PERMISSION_KEYS:
            continue
        if not fv:
            continue
        if nid != PUESTO_COMUN_ID and key in cv and (not fe or key in ce):
            continue
        db.session.add(
            PermisoPuesto(
                puesto_id=nid,
                permiso=key,
                habilitado=True,
                puede_editar=bool(fe),
            )
        )
        granted.append(key)
    mark_permission_keys_known(granted)


def grant_puesto_permissions(puesto_id: str, flags: dict[str, tuple[bool, bool]]) -> bool:
    """Suma recursos tildados al puesto, sin quitar los que ya tenía."""
    nid = (puesto_id or "").strip()
    if not nid:
        return False
    if nid == PUESTO_COMUN_ID:
        cur_v, cur_e = comunes_perm_sets()
    else:
        cur_v, cur_e = puesto_own_perm_sets(nid)
    merged: dict[str, tuple[bool, bool]] = {}
    for key in PERMISSION_KEYS:
        fv = key in cur_v
        fe = key in cur_e
        add_v, add_e = flags.get(key, (False, False))
        if add_v:
            fv = True
            fe = fe or add_e
        if fv:
            merged[key] = (True, fe)
    after_v = {k for k, (fv, _fe) in merged.items() if fv}
    after_e = {k for k, (fv, fe) in merged.items() if fv and fe}
    if after_v == cur_v and after_e == cur_e:
        return False
    replace_puesto_permissions(nid, merged)
    return True


def grant_user_permissions(user: User, flags: dict[str, tuple[bool, bool]]) -> bool:
    """Suma recursos tildados a la persona, sin revocar lo que ya tiene."""
    if user_uses_fixed_perm_template(user):
        return False
    view, edit = effective_perm_lists_for_user(user)
    view_s, edit_s = set(view), set(edit)
    try:
        existing = {
            (r.permiso or "").strip(): r
            for r in db.session.scalars(select(PermisoUsuario).where(PermisoUsuario.user_id == user.id)).all()
        }
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        return False
    changed = False
    granted: list[str] = []
    for key, (fv, fe) in flags.items():
        if key not in PERMISSION_KEYS or not fv:
            continue
        need_view = key not in view_s
        need_edit = bool(fe) and key not in edit_s
        if not need_view and not need_edit:
            continue
        row = existing.get(key)
        if row is None:
            db.session.add(
                PermisoUsuario(
                    user_id=user.id,
                    permiso=key,
                    habilitado=True,
                    puede_editar=bool(fe) or key in edit_s,
                )
            )
        else:
            row.habilitado = True
            if need_edit or fe:
                row.puede_editar = True
        changed = True
        granted.append(key)
    if granted:
        mark_permission_keys_known(granted)
    return changed


def replace_user_permission_overrides(
    user: User,
    flags: dict[str, tuple[bool, bool]],
    base_view: set[str],
    base_edit: set[str],
) -> None:
    """Guarda solo diffs respecto de plantilla+puesto (igual que el editor de usuario)."""
    db.session.execute(delete(PermisoUsuario).where(PermisoUsuario.user_id == user.id))
    if user_uses_fixed_perm_template(user):
        return
    for key, (fv, fe) in flags.items():
        if key not in PERMISSION_KEYS:
            continue
        in_bv = key in base_view
        in_be = key in base_edit
        if not fv:
            if in_bv:
                db.session.add(
                    PermisoUsuario(
                        user_id=user.id,
                        permiso=key,
                        habilitado=False,
                        puede_editar=False,
                    )
                )
            continue
        if not in_bv:
            db.session.add(
                PermisoUsuario(
                    user_id=user.id,
                    permiso=key,
                    habilitado=True,
                    puede_editar=fe,
                )
            )
            continue
        if fe != in_be:
            db.session.add(
                PermisoUsuario(
                    user_id=user.id,
                    permiso=key,
                    habilitado=True,
                    puede_editar=fe,
                )
            )
    granted = [k for k, (fv, _fe) in flags.items() if fv]
    mark_permission_keys_known(granted)


def organigrama_puesto_ids_for_user(user_id: int) -> list[str]:
    try:
        from app.services import sgi_anexo_service as anexo_svc

        return list(anexo_svc.organigrama_node_ids_for_user(int(user_id)))
    except Exception:
        db.session.rollback()
        return []


def base_perm_sets_for_role_and_puestos(
    stored_rol: str | None,
    puesto_ids: list[str] | set[str] | None,
) -> tuple[set[str], set[str]]:
    bv, be = role_template_perm_sets(stored_rol)
    pv, pe = view_edit_for_puestos(puesto_ids)
    return merge_puesto_into_role_template(bv, be, pv, pe)


def effective_perm_lists_for_user(user: User) -> tuple[list[str], list[str]]:
    if bool(getattr(user, "is_admin", False)):
        keys = list(PERMISSION_KEYS)
        return keys, keys
    try:
        rows = list(
            db.session.scalars(select(PermisoUsuario).where(PermisoUsuario.user_id == user.id)).all()
        )
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        rows = []
    pv, pe = view_edit_for_puestos(organigrama_puesto_ids_for_user(int(user.id)))
    return compute_session_perm_lists(
        getattr(user, "rol", None),
        rows,
        puesto_view=pv,
        puesto_edit=pe,
    )


def schema_ready() -> bool:
    try:
        insp = inspect(db.engine)
        names = set(insp.get_table_names())
        return "permisos_puesto" in names and "permisos_recursos_conocidos" in names
    except Exception:
        return False
