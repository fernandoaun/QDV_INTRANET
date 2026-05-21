from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import flash, g, has_request_context, redirect, request, session, url_for

from app.extensions import db
from app.models import PermisoUsuario, User
from app.constants import PERMISSION_KEYS
from app.user_roles import (
    ROLE_LOGISTICA,
    compute_session_perm_lists,
    normalize_stored_rol,
    normalized_role_is_global_read_only,
    user_is_global_read_only,
)

from sqlalchemy import select

F = TypeVar("F", bound=Callable[..., Any])

# Permisos que permiten ver el hub /produccion (además del flag general "produccion").
_PRODUCTION_HUB_PERMS: tuple[str, ...] = (
    "produccion",
    "salmuera",
    "bolson_registro",
    "reactor",
    "agua",
    "bolson_carga",
    "graficos",
    "lab_reactivos",
)

_ENTREGAS_ACCESS_PERMS: tuple[str, ...] = (
    "entregas",
    "entregas_programar",
    "entregas_cargar",
    "entregas_entregar",
)


def _user_has_logistica_role(user: User | None) -> bool:
    return user is not None and normalize_stored_rol(getattr(user, "rol", None)) == ROLE_LOGISTICA


def user_display_name(user: User | None) -> str:
    if user is None:
        return ""
    full = (getattr(user, "nombre_completo", None) or "").strip()
    if full:
        return full
    return (user.username or "").strip()


_STOCK_SECTION_VIEW_PERMS: tuple[str, ...] = (
    "stock_ingreso_mp",
    "stock_ingreso_lab",
    "stock_consumos",
    "stock_existencias",
    "stock_historial",
    "stock_alertas_config",
)


def user_can_access_production_hub(user: User | None) -> bool:
    """True si el usuario puede abrir la pantalla agrupada Producción y sus tarjetas."""
    if user is None:
        return False
    return any(user_can(user, p) for p in _PRODUCTION_HUB_PERMS)


def user_can_view_admin_configuration(user: User | None) -> bool:
    """
    Pantallas de administración en modo consulta (usuarios, equipos, catálogos de entregas).
    Administrador o quien tenga permiso de vista «admin_usuarios» (p. ej. perfiles Angel o SGI).
    """
    if user is None:
        return False
    if user.is_admin:
        return True
    return user_can(user, "admin_usuarios")


def user_can_access_vencimientos(user: User | None) -> bool:
    """Solo administrador o perfiles solo lectura total (Angel, SGI)."""
    if user is None:
        return False
    if user.is_admin:
        return True
    return normalized_role_is_global_read_only(normalize_stored_rol(getattr(user, "rol", None)))


def user_can_manage_vencimientos(user: User | None) -> bool:
    """Alta/edición/baja: únicamente administrador."""
    return user is not None and bool(user.is_admin)


def user_can_access_sgi(user: User | None) -> bool:
    """Administrador, perfiles Angel/SGI o usuarios con permiso sgi_hub."""
    if user is None:
        return False
    if user.is_admin:
        return True
    if normalized_role_is_global_read_only(normalize_stored_rol(getattr(user, "rol", None))):
        return True
    return user_can(user, "sgi_hub")


def user_can_edit_sgi_documentos(user: User | None) -> bool:
    """Crear/editar documentos: administrador o permiso sgi_documentos_edit (no Angel/SGI)."""
    if user is None or user_is_global_read_only(user):
        return False
    if user.is_admin:
        return True
    return user_can_edit(user, "sgi_documentos_edit")


def user_can_delete_sgi_documentos(user: User | None) -> bool:
    """Eliminar documentos: únicamente administrador."""
    return user is not None and bool(user.is_admin)


def user_can_view_sgi_obsoletos(user: User | None) -> bool:
    """Documentos obsoletos: administrador o perfiles SGI / Angel (solo lectura total)."""
    if user is None:
        return False
    if user.is_admin:
        return True
    return normalized_role_is_global_read_only(normalize_stored_rol(getattr(user, "rol", None)))


def user_can_access_planificacion(user: User | None) -> bool:
    if user is None:
        return False
    return user_can(user, "planificacion")


def user_can_access_mantenimiento(user: User | None) -> bool:
    if user is None:
        return False
    return (
        user_can(user, "mantenimiento")
        or user_can(user, "mantenimiento_equipos")
        or user_can(user, "mantenimiento_correctivos")
        or user_can(user, "mantenimiento_preventivos")
        or user_can(user, "mantenimiento_recursos")
        or user_can(user, "mantenimiento_predictivo")
    )


def user_can_access_entregas_hub(user: User | None) -> bool:
    """Acceso al módulo Entregas solo con permisos explícitos del árbol entregas_* (sin heredar Producción)."""
    if user is None:
        return False
    if _user_has_logistica_role(user):
        return True
    return any(user_can(user, p) for p in _ENTREGAS_ACCESS_PERMS)


def has_permission(user: User | None, perm: str) -> bool:
    """Fuente de verdad para permiso funcional de vista (alias de user_can / sesión)."""
    return user_can(user, perm)


def user_may_view_entregas_programar(user: User | None) -> bool:
    """Pantallas de programación: vista explícita o permiso padre 'entregas'."""
    if user is None:
        return False
    return user_can(user, "entregas_programar") or user_can(user, "entregas")


def user_can_entregas_programar_effective(user: User | None) -> bool:
    """Edición de programación / altas (no amplía por otros módulos)."""
    if user is None:
        return False
    if _user_has_logistica_role(user):
        return True
    return user_can_edit(user, "entregas_programar")


def user_can_entregas_cargar_effective(user: User | None) -> bool:
    if user is None:
        return False
    if _user_has_logistica_role(user):
        return True
    return user_can_edit(user, "entregas_cargar")


def user_can_entregas_entregar_effective(user: User | None) -> bool:
    if user is None:
        return False
    if _user_has_logistica_role(user):
        return True
    return user_can_edit(user, "entregas_entregar")


def user_can_edit_entregas_any_action(user: User | None) -> bool:
    if user is None:
        return False
    return (
        user_can_entregas_programar_effective(user)
        or user_can_entregas_cargar_effective(user)
        or user_can_entregas_entregar_effective(user)
    )


_STOCK_EDIT_SECTION_PERMS: tuple[str, ...] = (
    "stock_hub",
    "stock_ingreso_mp",
    "stock_ingreso_lab",
    "stock_consumos",
    "stock_existencias",
    "stock_historial",
    "stock_alertas_config",
)


def user_can_edit_stock_hub_aggregate(user: User | None) -> bool:
    """Edición en el hub de stock si puede editar el módulo o alguna subsección."""
    if user is None:
        return False
    if user.is_admin:
        return True
    return any(user_can_edit(user, k) for k in _STOCK_EDIT_SECTION_PERMS)


def perm_sets_for_user(user: User) -> tuple[list[str], list[str]]:
    """Listas de permisos de vista y edición (misma lógica que la sesión web)."""
    if user.is_admin:
        p = list(PERMISSION_KEYS)
        return p, p
    rows = list(
        db.session.scalars(
            select(PermisoUsuario).where(PermisoUsuario.user_id == user.id)
        ).all()
    )
    stored = normalize_stored_rol(getattr(user, "rol", None))
    p_view, p_edit = compute_session_perm_lists(stored, rows)
    return list(p_view), list(p_edit)


def current_user() -> User | None:
    if has_request_context():
        u_api = getattr(g, "_qdv_api_user", None)
        if u_api is not None:
            return u_api
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, int(uid))


def set_session_for_user(user: User) -> None:
    session["user_id"] = user.id
    session.permanent = True
    p_view, p_edit = perm_sets_for_user(user)
    session["perms"] = p_view
    session["perms_edit"] = p_edit


def user_can(user: User | None, perm: str) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    if has_request_context():
        override = getattr(g, "_qdv_api_perms_view", None)
        if override is not None:
            return perm in override
    return perm in set(session.get("perms", []))


def user_can_edit(user: User | None, perm: str) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    if user_is_global_read_only(user):
        return False
    if has_request_context():
        override = getattr(g, "_qdv_api_perms_edit", None)
        if override is not None:
            return perm in override
    return perm in set(session.get("perms_edit", []))


def stock_ingreso_perm_for_categoria(categoria: str | None) -> str:
    c = (categoria or "").strip()
    if c == "laboratorio":
        return "stock_ingreso_lab"
    return "stock_ingreso_mp"


def user_can_access_stock_hub(user: User | None) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return user_can(user, "stock_hub") or any(user_can(user, k) for k in _STOCK_SECTION_VIEW_PERMS)


def user_can_view_stock_historial(user: User | None) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return user_can(user, "stock_historial")


def user_can_view_stock_ingreso_categoria(user: User | None, categoria: str | None) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return user_can(user, stock_ingreso_perm_for_categoria(categoria))


def user_can_edit_stock_ingreso_categoria(user: User | None, categoria: str | None) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return user_can_edit(user, stock_ingreso_perm_for_categoria(categoria))


def user_can_edit_stock_catalogo_alta(user: User | None) -> bool:
    """Alta de producto en catálogo (sin stock): mismo criterio que edición de ingreso MP o laboratorio."""
    if user is None:
        return False
    if user.is_admin:
        return True
    return user_can_edit_stock_ingreso_categoria(user, "materia_prima") or user_can_edit_stock_ingreso_categoria(
        user, "laboratorio"
    )


def user_can_view_stock_consumos(user: User | None) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return user_can(user, "stock_consumos")


def user_can_edit_stock_consumos(user: User | None) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return user_can_edit(user, "stock_consumos")


def user_can_view_stock_existencias(user: User | None) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return user_can(user, "stock_existencias")


def endpoint_requires_operational_shift_for_post(endpoint: str | None) -> bool:
    """
    Mutaciones de planta (producción/stock en panel) que exigen turno activo (perfil operaciones).
    Entregas (logística) no entran: cada vista valida permisos entregas_*.
    Las rutas del blueprint shift y auth quedan exentas (se validan adentro).
    """
    ep = (endpoint or "").strip()
    if not ep:
        return False
    if ep.startswith("shift."):
        return False
    if ep.startswith("auth."):
        return False
    if ep.startswith("main."):
        return False
    if ep.startswith("admin_users."):
        return False
    prefixes = (
        "produccion.salmuera",
        "produccion.reactor",
        "produccion.agua",
        "produccion.columnas",
        "produccion.bolson",
        "produccion.stock_",
        "produccion.operador_agregar",
        "produccion.lab_reactivos_registrar_consumo",
        # entregas.*: fuera del turno operativo de planta; permisos entregas_* en cada ruta.
    )
    return any(ep.startswith(p) for p in prefixes)


def endpoint_permission_key(endpoint: str | None) -> str | None:
    ep = (endpoint or "").strip()
    if not ep:
        return None
    if ep == "main.manual":
        return "manual"
    if ep.startswith("produccion.salmuera"):
        return "salmuera"
    if ep.startswith("produccion.reactor"):
        return "reactor"
    if ep.startswith("produccion.agua") or ep.startswith("produccion.columnas"):
        return "agua"
    if ep.startswith("produccion.bolson"):
        return "bolson_registro"
    if ep.startswith("produccion.stock_ingreso") or ep.startswith("produccion.stock_ver"):
        return "bolson_registro"
    if ep.startswith("produccion.stock_consumo"):
        return "bolson_carga"
    if ep.startswith("produccion.graficos"):
        return "graficos"
    if ep.startswith("produccion.lab_reactivos"):
        return "lab_reactivos"
    return None


def user_shift_may_write_operational(user: User | None, session: object | None) -> bool:
    """
    Perfil operaciones: True solo si puede mutar datos operativos (turno propio, sin pendiente, etc.).
    Admin y otros perfiles: True (no aplica restricción por turno).
    """
    from app.services import shift_handover_service as sh

    if user is None or user.is_admin:
        return True
    if not sh.user_participates_operational_shift(user):
        return True
    declined = False
    if session is not None and hasattr(session, "get"):
        declined = bool(session.get(sh.SESSION_KEY_SHIFT_DECLINED))
    return sh.assert_may_mutate_operational(user, declined).allowed


def page_can_edit_effective(user: User | None, endpoint: str | None, session: object | None) -> bool:
    """
    Edición en pantalla: permisos de perfil + turno operativo (solo perfil operaciones).
    Las rutas shift.* se eximen del chequeo de turno en UI (cada vista valida en servidor).
    """
    if user is not None and user_is_global_read_only(user):
        return False
    if not user_can_edit_endpoint(user, endpoint):
        return False
    if user is None:
        return False
    ep = (endpoint or "").strip()
    if ep.startswith("shift."):
        return True
    if user.is_admin:
        return True
    if ep.startswith("entregas."):
        # Programar / cargar / entregar: ya exige permisos entregas_*; no ligar a turno de planta.
        return True
    from app.services import shift_handover_service as sh

    if not sh.user_participates_operational_shift(user):
        return True
    return user_shift_may_write_operational(user, session)


def user_can_edit_endpoint(user: User | None, endpoint: str | None) -> bool:
    ep = (endpoint or "").strip()
    if ep in ("entregas.api_lugares_por_cliente", "entregas.api_marcas_producto_terminado"):
        # Endpoints JSON auxiliares; no habilitan edición de página (formularios usan otros endpoints).
        return False
    if ep.startswith("entregas.catalogos"):
        return bool(user and user.is_admin)
    if ep == "entregas.nueva":
        return user_can_entregas_programar_effective(user)
    if ep == "entregas.editar":
        return user_can_edit(user, "entregas_programar") or user_can_edit(user, "entregas_cargar")
    if ep == "entregas.historial":
        return user_can_entregas_programar_effective(user)
    if ep.startswith("entregas."):
        return user_can_edit_entregas_any_action(user)
    if ep.startswith("vencimientos."):
        return user_can_manage_vencimientos(user)
    if ep.startswith("sgi."):
        return user_can_edit_sgi_documentos(user)
    if ep.startswith("planificacion."):
        return user_can_edit(user, "planificacion")
    if ep.startswith("mantenimiento.equipos") or ep.startswith("mantenimiento.equipo") or ep.startswith(
        "mantenimiento.component"
    ):
        return user_can_edit(user, "mantenimiento_equipos")
    if ep.startswith("mantenimiento.correctivos") or ep.startswith("mantenimiento.reportar") or ep.startswith(
        "mantenimiento.failure"
    ):
        return user_can_edit(user, "mantenimiento_correctivos")
    if ep.startswith("mantenimiento.preventivos") or ep.startswith("mantenimiento.orden"):
        return user_can_edit(user, "mantenimiento_preventivos")
    if ep.startswith("mantenimiento.recursos"):
        return user_can_edit(user, "mantenimiento_recursos")
    if ep.startswith("mantenimiento.predictivo"):
        return user_can_edit(user, "mantenimiento_predictivo")
    if ep.startswith("mantenimiento."):
        return user_can_edit(user, "mantenimiento")
    if ep == "produccion.stock_consumo":
        return user_can_edit_stock_consumos(user)
    if ep == "produccion.stock_ver":
        return user_can_edit(user, "stock_existencias")
    if ep == "produccion.stock_hub":
        return user_can_edit_stock_hub_aggregate(user)
    if ep == "produccion.stock_ingreso":
        # Usa categoría activa (GET/POST) para determinar modo edición.
        cat = (request.values.get("categoria") or "materia_prima").strip()
        return user_can_edit_stock_ingreso_categoria(user, cat)
    key = endpoint_permission_key(endpoint)
    if key is None:
        if user is None:
            return False
        if user.is_admin:
            return True
        # Hub, panel u otras vistas sin clave explícita: editar solo si el usuario tiene algún permiso de edición.
        if has_request_context():
            return len(session.get("perms_edit", [])) > 0
        return False
    return user_can_edit(user, key)


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.url))
        if not user.activo:
            session.clear()
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return cast(F, wrapped)


def admin_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.url))
        if not user.activo or not user.is_admin:
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)

    return cast(F, wrapped)


def permission_required(perm: str):
    def decorator(view: F) -> F:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.login", next=request.url))
            if not user_can(user, perm):
                flash("No tenés permiso para acceder a esta sección.", "warning")
                return redirect(url_for("main.dashboard"))
            if request.method.upper() not in {"GET", "HEAD", "OPTIONS"} and not user_can_edit(user, perm):
                flash("Tenés acceso de solo lectura en este módulo.", "warning")
                return redirect(request.referrer or url_for("main.dashboard"))
            return view(*args, **kwargs)

        return cast(F, wrapped)

    return decorator
