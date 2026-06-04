from __future__ import annotations


def test_administracion_role_template_stock_ingresos(app):
    from app.auth_utils import (
        user_can_access_production_hub,
        user_can_access_stock_hub,
        user_can_edit_stock_ingreso_categoria,
        user_can_view_stock_ingreso_categoria,
    )
    from app.models import User
    from app.services import shift_handover_service as sh
    from app.user_roles import ROLE_ADMINISTRACION, compute_session_perm_lists, role_template_perm_sets

    view, edit = role_template_perm_sets(ROLE_ADMINISTRACION)
    assert "stock_ingreso_mp" in view
    assert "stock_ingreso_lab" in view
    assert "stock_ingreso_mp" in edit
    assert "stock_ingreso_lab" in edit
    assert "stock_consumos" not in view
    assert "salmuera" not in view

    p_view, p_edit = compute_session_perm_lists(ROLE_ADMINISTRACION, [])
    assert "stock_ingreso_mp" in p_view
    assert "stock_ingreso_lab" in p_edit

    user = User(
        username="pytest_administracion",
        password_hash="x",
        is_admin=False,
        activo=True,
        rol=ROLE_ADMINISTRACION,
    )

    assert not sh.user_participates_operational_shift(user)

    with app.test_request_context("/produccion/stock"):
        from flask import session

        session["perms"] = p_view
        session["perms_edit"] = p_edit

        assert user_can_access_stock_hub(user)
        assert user_can_access_production_hub(user)
        assert user_can_view_stock_ingreso_categoria(user, "materia_prima")
        assert user_can_view_stock_ingreso_categoria(user, "laboratorio")
        assert user_can_edit_stock_ingreso_categoria(user, "materia_prima")
        assert user_can_edit_stock_ingreso_categoria(user, "laboratorio")


def test_validate_rol_accepts_administracion():
    from app.user_roles import ROLE_ADMINISTRACION, validate_rol_submitted

    assert validate_rol_submitted("Administración") == ROLE_ADMINISTRACION
    assert validate_rol_submitted("administracion") == ROLE_ADMINISTRACION
