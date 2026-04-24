from __future__ import annotations


def test_logistica_can_operate_entregas_even_with_stale_session(app):
    from flask import session

    from app.auth_utils import (
        user_can_access_entregas_hub,
        user_can_entregas_cargar_effective,
        user_can_entregas_entregar_effective,
        user_can_edit_entregas_any_action,
    )
    from app.models import User
    from app.user_roles import ROLE_LOGISTICA

    user = User(username="pytest_logistica", password_hash="x", is_admin=False, activo=True, rol=ROLE_LOGISTICA)

    with app.test_request_context("/entregas/gestion"):
        session["perms"] = []
        session["perms_edit"] = []

        assert user_can_access_entregas_hub(user)
        assert user_can_entregas_cargar_effective(user)
        assert user_can_entregas_entregar_effective(user)
        assert user_can_edit_entregas_any_action(user)
