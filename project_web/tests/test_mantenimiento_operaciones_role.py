from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from app.models import User
from app.services import shift_handover_service as sh
from app.services import sgi_documento_perfil_service as perfil_svc
from app.user_roles import (
    ROLE_MANTENIMIENTO,
    ROLE_MANTENIMIENTO_OPERACIONES,
    ROLE_OPERACIONES,
    compute_session_perm_lists,
    role_covers_perfiles,
    role_label,
    role_template_perm_sets,
    validate_rol_submitted,
)


def test_validate_and_label_mantenimiento_operaciones():
    assert validate_rol_submitted("Mantenimiento y operaciones") == ROLE_MANTENIMIENTO_OPERACIONES
    assert validate_rol_submitted("mantenimiento_operaciones") == ROLE_MANTENIMIENTO_OPERACIONES
    assert role_label(ROLE_MANTENIMIENTO_OPERACIONES) == "Mantenimiento y operaciones"


def test_template_is_union_of_mantenimiento_and_operaciones():
    view, edit = role_template_perm_sets(ROLE_MANTENIMIENTO_OPERACIONES)
    op_view, _ = role_template_perm_sets(ROLE_OPERACIONES)
    mant_view, _ = role_template_perm_sets(ROLE_MANTENIMIENTO)

    assert view == (op_view | mant_view)
    assert edit == view
    assert "mantenimiento_equipos" in view
    assert "bolson_carga" in view
    assert "entregas_cargar" in view

    session_view, session_edit = compute_session_perm_lists(ROLE_MANTENIMIENTO_OPERACIONES, [])
    assert "mantenimiento_predictivo" in session_view
    assert "salmuera" in session_edit


def test_covers_operaciones_and_mantenimiento_for_sgi():
    covered = role_covers_perfiles(ROLE_MANTENIMIENTO_OPERACIONES)
    assert ROLE_MANTENIMIENTO_OPERACIONES in covered
    assert ROLE_OPERACIONES in covered
    assert ROLE_MANTENIMIENTO in covered


def test_participates_operational_shift(app):
    user = User(
        username="pytest_mant_ops",
        password_hash="x",
        is_admin=False,
        activo=True,
        rol=ROLE_MANTENIMIENTO_OPERACIONES,
    )
    assert sh.user_participates_operational_shift(user)

    only_mant = User(
        username="pytest_only_mant",
        password_hash="x",
        is_admin=False,
        activo=True,
        rol=ROLE_MANTENIMIENTO,
    )
    assert not sh.user_participates_operational_shift(only_mant)


def test_sgi_users_with_perfiles_includes_combined_role(app):
    with app.app_context():
        from app.extensions import db

        combo = User(
            username="pytest_combo_sgi",
            password_hash=generate_password_hash("x"),
            rol=ROLE_MANTENIMIENTO_OPERACIONES,
            activo=True,
        )
        op = User(
            username="pytest_op_sgi2",
            password_hash=generate_password_hash("x"),
            rol=ROLE_OPERACIONES,
            activo=True,
        )
        db.session.add_all([combo, op])
        db.session.commit()

        for_ops = perfil_svc.users_with_perfiles([ROLE_OPERACIONES])
        names = {u.username for u in for_ops}
        assert "pytest_combo_sgi" in names
        assert "pytest_op_sgi2" in names

        for_combo = perfil_svc.users_with_perfiles([ROLE_MANTENIMIENTO_OPERACIONES])
        combo_names = {u.username for u in for_combo}
        assert "pytest_combo_sgi" in combo_names
        assert "pytest_op_sgi2" not in combo_names


def test_admin_can_save_mantenimiento_operaciones_permissions(auth_client, app):
    """Guardar perfil+permisos no debe 500 (antes fallaba audit_svc.json_preview)."""
    from app.constants import PERMISSION_FORM_KEYS, PERMISSION_KEYS
    from app.extensions import db
    from app.models import PermisoUsuario
    from app.user_roles import role_template_perm_sets

    with app.app_context():
        miguel = User(
            username="miguel_perm_save",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_MANTENIMIENTO,
            nombre_completo="Miguel",
        )
        db.session.add(miguel)
        db.session.commit()
        uid = miguel.id

    r = auth_client.get(f"/admin/usuarios/{uid}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None

    bv, _ = role_template_perm_sets(ROLE_MANTENIMIENTO_OPERACIONES)
    data = {
        "action": "core",
        "username": "miguel_perm_save",
        "nombre_completo": "Miguel",
        "rol": ROLE_MANTENIMIENTO_OPERACIONES,
        "activo": "1",
        "csrf_token": m.group(1),
    }
    for key in PERMISSION_FORM_KEYS:
        if key in bv:
            data[f"permv_{key}"] = "1"
            data[f"perme_{key}"] = "1"
    extras = [k for k in PERMISSION_KEYS if k not in bv][:3]
    for k in extras:
        data[f"permv_{k}"] = "1"
        data[f"perme_{k}"] = "1"

    r2 = auth_client.post(f"/admin/usuarios/{uid}", data=data, follow_redirects=True)
    body = r2.get_data(as_text=True)
    assert r2.status_code == 200
    assert "error interno" not in body.lower()
    assert "Usuario actualizado" in body

    with app.app_context():
        u = db.session.get(User, uid)
        assert u is not None
        assert u.rol == ROLE_MANTENIMIENTO_OPERACIONES
        rows = list(db.session.query(PermisoUsuario).filter_by(user_id=uid).all())
        assert {r.permiso for r in rows} >= set(extras)
