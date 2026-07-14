"""
Perfiles de usuario (rol almacenado) y resolución de permisos efectivos.

- «solo_lectura_total» (Angel): ve todos los módulos y datos; no puede mutar datos operativos, pero sí ejecutar aprobaciones (SGI, vacaciones si es responsable, etc.).
- «sgi»: vista global en todo el sistema, con edición limitada al módulo SGI.
- «administracion»: carga ingresos de materia prima y laboratorio (stock); no toma turno operativo.
- «mantenimiento_operaciones»: plantilla unión de mantenimiento + operaciones; puede tomar turno de planta.
- «laboratorista»: sin plantilla operativa en el panel; no toma turno ni muta datos (el acceso web está bloqueado en login).
  En planta se registra junto al turno del operador responsable, no como usuario operativo independiente.
- Los permisos finales = plantilla del rol efectivo, aplicando filas en `permisos_usuario` como overrides:
  `habilitado=True` fuerza vista (y puede ajustar edición); `habilitado=False` revoca aunque el perfil lo incluya.
- Valores desconocidos en BD se normalizan a «operaciones» (seguro, sin borrar usuarios).
- «pasante» en datos legados se normaliza a «laboratorista» (ver migración).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.constants import PERMISSION_KEYS

if TYPE_CHECKING:
    from app.models import PermisoUsuario

ROLE_ADMINISTRADOR = "administrador"
ROLE_OPERACIONES = "operaciones"
ROLE_LOGISTICA = "logistica"
ROLE_ADMINISTRACION = "administracion"
ROLE_MANTENIMIENTO = "mantenimiento"
ROLE_MANTENIMIENTO_OPERACIONES = "mantenimiento_operaciones"
ROLE_SOLO_LECTURA_TOTAL = "solo_lectura_total"
ROLE_SGI = "sgi"
ROLE_LABORATORISTA = "laboratorista"

USER_ROLES_ORDERED: tuple[str, ...] = (
    ROLE_ADMINISTRADOR,
    ROLE_OPERACIONES,
    ROLE_LOGISTICA,
    ROLE_ADMINISTRACION,
    ROLE_MANTENIMIENTO,
    ROLE_MANTENIMIENTO_OPERACIONES,
    ROLE_SOLO_LECTURA_TOTAL,
    ROLE_SGI,
    ROLE_LABORATORISTA,
)

ROLE_LABELS: dict[str, str] = {
    ROLE_ADMINISTRADOR: "Administrador",
    ROLE_OPERACIONES: "Operaciones",
    ROLE_LOGISTICA: "Logística",
    ROLE_ADMINISTRACION: "Administración",
    ROLE_MANTENIMIENTO: "Mantenimiento",
    ROLE_MANTENIMIENTO_OPERACIONES: "Mantenimiento y operaciones",
    ROLE_SOLO_LECTURA_TOTAL: "Angel",
    ROLE_SGI: "SGI",
    ROLE_LABORATORISTA: "Laboratorista",
}

# Alias por si migraron textos viejos o se cargó a mano en BD.
_LEGACY_ALIASES: dict[str, str] = {
    "admin": ROLE_ADMINISTRADOR,
    "administrator": ROLE_ADMINISTRADOR,
    "operario": ROLE_OPERACIONES,
    "operador": ROLE_OPERACIONES,
    "operator": ROLE_OPERACIONES,
    "logística": ROLE_LOGISTICA,
    "logistica": ROLE_LOGISTICA,
    "administración": ROLE_ADMINISTRACION,
    "administracion": ROLE_ADMINISTRACION,
    "administration": ROLE_ADMINISTRACION,
    "mantenimiento": ROLE_MANTENIMIENTO,
    "mantenimiento y operaciones": ROLE_MANTENIMIENTO_OPERACIONES,
    "mantenimiento_y_operaciones": ROLE_MANTENIMIENTO_OPERACIONES,
    "mantenimiento-operaciones": ROLE_MANTENIMIENTO_OPERACIONES,
    "pasante": ROLE_LABORATORISTA,
    "practicante": ROLE_LABORATORISTA,
    "pasant": ROLE_LABORATORISTA,
    "angel": ROLE_SOLO_LECTURA_TOTAL,
    "read_only_full": ROLE_SOLO_LECTURA_TOTAL,
    "solo_lectura": ROLE_SOLO_LECTURA_TOTAL,
}
_BASE_OPERACIONES: frozenset[str] = frozenset(
    {
        "produccion",
        "manual",
        "salmuera",
        "bolson_carga",
        "bolson_registro",
        "stock_hub",
        "stock_ingreso_mp",
        "stock_ingreso_lab",
        "stock_consumos",
        "stock_existencias",
        "stock_historial",
        "stock_alertas_config",
        "reactor",
        "agua",
        "graficos",
        "lab_reactivos",
        "entregas",
        "entregas_cargar",
        "recepcion",
        "despacho",
        "planificacion",
        "mantenimiento",
        "mantenimiento_correctivos",
    }
)

_BASE_LOGISTICA: frozenset[str] = frozenset(
    {
        "manual",
        "entregas",
        "entregas_programar",
        "entregas_entregar",
        "despacho",
        "recepcion",
        "stock_hub",
        "stock_existencias",
        "stock_historial",
        "planificacion",
    }
)

_BASE_ADMINISTRACION: frozenset[str] = frozenset(
    {
        "manual",
        "stock_hub",
        "stock_ingreso_mp",
        "stock_ingreso_lab",
        "stock_existencias",
        "stock_historial",
    }
)

_BASE_MANTENIMIENTO: frozenset[str] = frozenset(
    {
        "manual",
        "produccion",
        "salmuera",
        "reactor",
        "agua",
        "graficos",
        "lab_reactivos",
        "bolson_registro",
        "stock_hub",
        "stock_existencias",
        "stock_historial",
        "planificacion",
        "mantenimiento",
        "mantenimiento_equipos",
        "mantenimiento_correctivos",
        "mantenimiento_preventivos",
        "mantenimiento_recursos",
        "mantenimiento_predictivo",
    }
)

_ALL_PERM_KEYS: frozenset[str] = frozenset(PERMISSION_KEYS)


def normalize_stored_rol(raw: str | None) -> str:
    """Devuelve uno de USER_ROLES_ORDERED; valores ilegibles → operaciones."""
    if raw is None:
        return ROLE_OPERACIONES
    s = str(raw).strip().lower()
    if not s:
        return ROLE_OPERACIONES
    if s in _LEGACY_ALIASES:
        return _LEGACY_ALIASES[s]
    if s in USER_ROLES_ORDERED:
        return s
    return ROLE_OPERACIONES


def role_covers_perfiles(stored_rol: str | None) -> frozenset[str]:
    """
    Perfiles con los que coincide el rol al filtrar SGI / chat por sector.
    «mantenimiento_operaciones» abarca mantenimiento y operaciones además de sí mismo.
    """
    n = normalize_stored_rol(stored_rol)
    if n == ROLE_MANTENIMIENTO_OPERACIONES:
        return frozenset({ROLE_MANTENIMIENTO_OPERACIONES, ROLE_MANTENIMIENTO, ROLE_OPERACIONES})
    return frozenset({n})


def role_matches_target_perfil(stored_rol: str | None, target_perfil: str | None) -> bool:
    """True si el rol del usuario debe recibir avisos / acceso de ese perfil objetivo."""
    target = normalize_stored_rol(target_perfil)
    return target in role_covers_perfiles(stored_rol)


def normalized_role_is_global_read_only(normalized_stored_rol: str) -> bool:
    """Perfiles con vista total y sin permisos de edición en ningún módulo (solo Angel)."""
    return normalized_stored_rol == ROLE_SOLO_LECTURA_TOTAL


def normalized_role_has_global_view(normalized_stored_rol: str) -> bool:
    """Perfiles con vista total global (Angel y SGI)."""
    return normalized_stored_rol in (ROLE_SOLO_LECTURA_TOTAL, ROLE_SGI)


def user_is_global_read_only(user: object | None) -> bool:
    """True si el perfil es solo lectura total global (Angel)."""
    if user is None or bool(getattr(user, "is_admin", False)):
        return False
    return normalized_role_is_global_read_only(normalize_stored_rol(getattr(user, "rol", None)))


def effective_role_for_permissions(stored_rol: str | None) -> str:
    """
    Rol lógico para permisos (plantillas). «laboratorista» no hereda plantilla operativa.
    «administrador» se maneja con is_admin + sesión completa; se devuelve igual por simetría.
    """
    return normalize_stored_rol(stored_rol)


def role_label(stored_rol: str | None) -> str:
    """Etiqueta para UI según rol normalizado."""
    n = normalize_stored_rol(stored_rol)
    return ROLE_LABELS.get(n, ROLE_LABELS[ROLE_OPERACIONES])


def _base_view_edit_for_effective_role(effective: str) -> tuple[set[str], set[str]]:
    """Pares (ver, editar) incluidos en la plantilla del rol efectivo."""
    keys = _ALL_PERM_KEYS
    if effective == ROLE_ADMINISTRADOR:
        full = set(keys)
        return full, full
    if effective == ROLE_OPERACIONES:
        v = set(_BASE_OPERACIONES) & keys
        return v, set(v)
    if effective == ROLE_LOGISTICA:
        v = set(_BASE_LOGISTICA) & keys
        return v, set(v)
    if effective == ROLE_ADMINISTRACION:
        v = set(_BASE_ADMINISTRACION) & keys
        return v, set(v)
    if effective == ROLE_MANTENIMIENTO:
        v = set(_BASE_MANTENIMIENTO) & keys
        return v, set(v)
    if effective == ROLE_MANTENIMIENTO_OPERACIONES:
        v = (set(_BASE_OPERACIONES) | set(_BASE_MANTENIMIENTO)) & keys
        return v, set(v)
    if effective == ROLE_SGI:
        return set(_ALL_PERM_KEYS), {"sgi_documentos_edit"}
    if normalized_role_is_global_read_only(effective):
        return set(_ALL_PERM_KEYS), set()
    if effective == ROLE_LABORATORISTA:
        return set(), set()
    return set(), set()


def apply_permiso_rows_over_template(
    base_view: set[str],
    base_edit: set[str],
    rows: list[PermisoUsuario],
) -> tuple[set[str], set[str]]:
    """
    Parte de la plantilla del rol y aplica filas `permisos_usuario` en orden.
    - habilitado=False: quita el permiso aunque la plantilla lo otorgue.
    - habilitado=True: asegura vista; puede_editar ajusta si puede mutar ese módulo.
    """
    view = set(base_view) & _ALL_PERM_KEYS
    edit = set(base_edit) & _ALL_PERM_KEYS
    edit &= view
    for r in rows:
        p = (r.permiso or "").strip()
        if p not in _ALL_PERM_KEYS:
            continue
        if not r.habilitado:
            view.discard(p)
            edit.discard(p)
            continue
        view.add(p)
        if bool(getattr(r, "puede_editar", True)):
            edit.add(p)
        else:
            edit.discard(p)
    edit &= view
    return view, edit


def role_template_perm_sets(stored_rol: str | None) -> tuple[set[str], set[str]]:
    """Conjuntos de vista/edición definidos solo por el perfil (sin tabla)."""
    eff = effective_role_for_permissions(stored_rol)
    bv, be = _base_view_edit_for_effective_role(eff)
    v = set(bv) & _ALL_PERM_KEYS
    e = set(be) & _ALL_PERM_KEYS
    e &= v
    return v, e


def compute_session_perm_lists(stored_rol: str | None, rows: list[PermisoUsuario]) -> tuple[list[str], list[str]]:
    """
    Lista final para session['perms'] y session['perms_edit'].
    Plantilla(rol_efectivo) + overrides en `permisos_usuario` (incluye revocaciones habilitado=False).
    """
    eff = effective_role_for_permissions(stored_rol)
    if eff == ROLE_SGI:
        # Rol SGI: capacidad fija de edición en SGI aunque existan overrides legacy en BD.
        return sorted(_ALL_PERM_KEYS), ["sgi_documentos_edit"]
    if normalized_role_is_global_read_only(eff):
        # Vista total fija; sin edición aunque existan filas en permisos_usuario.
        return sorted(_ALL_PERM_KEYS), []
    bv, be = _base_view_edit_for_effective_role(eff)
    view, edit = apply_permiso_rows_over_template(bv, be, rows)
    return sorted(view), sorted(edit)


def validate_rol_submitted(raw: str | None) -> str | None:
    """None si el valor POST es inválido (no normalizar silenciosamente en formularios admin)."""
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip().lower()
    if s in _LEGACY_ALIASES:
        s = _LEGACY_ALIASES[s]
    if s in USER_ROLES_ORDERED:
        return s
    return None
