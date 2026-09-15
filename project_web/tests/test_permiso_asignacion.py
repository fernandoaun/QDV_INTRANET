from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from app.constants import PERMISSION_KEYS
from app.extensions import db
from app.models import PermisoRecursoConocido, PermisoUsuario, User
from app.services import permiso_asignacion_service as perm_asig
from app.user_roles import ROLE_ADMINISTRACION, ROLE_OPERACIONES, compute_session_perm_lists


def test_permission_catalog_matches_tree():
    from app.constants import PERMISSION_FORM_KEYS, PERMISSION_KEYS

    assert set(PERMISSION_KEYS) == set(PERMISSION_FORM_KEYS)


def test_puesto_grant_adds_perm_beyond_role_template():
    view, edit = compute_session_perm_lists(
        ROLE_ADMINISTRACION,
        [],
        puesto_view={"planificacion"},
        puesto_edit={"planificacion"},
    )
    assert "planificacion" in view
    assert "planificacion" in edit
    assert "stock_ingreso_mp" in view
    assert "salmuera" not in view


def test_user_override_revokes_puesto_grant():
    row = PermisoUsuario(
        user_id=1,
        permiso="planificacion",
        habilitado=False,
        puede_editar=False,
    )
    view, edit = compute_session_perm_lists(
        ROLE_ADMINISTRACION,
        [row],
        puesto_view={"planificacion"},
        puesto_edit={"planificacion"},
    )
    assert "planificacion" not in view
    assert "planificacion" not in edit
    assert "stock_ingreso_mp" in view


def test_new_unassigned_resources_and_acknowledge(app):
    with app.app_context():
        perm_asig.ensure_schema()
        assert perm_asig.new_unassigned_resources() == []
        row = db.session.get(PermisoRecursoConocido, "personal")
        assert row is not None
        db.session.delete(row)
        db.session.commit()
        pending = {r["key"] for r in perm_asig.new_unassigned_resources()}
        assert "personal" in pending
        n = perm_asig.acknowledge_new_permission_keys()
        assert n >= 1
        assert perm_asig.new_unassigned_resources() == []


def test_replace_puesto_permissions_marks_known(app):
    with app.app_context():
        perm_asig.ensure_schema()
        row = db.session.get(PermisoRecursoConocido, "personal")
        if row is not None:
            db.session.delete(row)
            db.session.commit()
        perm_asig.replace_puesto_permissions(
            "choferes",
            {"personal": (True, True), "planificacion": (True, False)},
        )
        db.session.commit()
        view, edit = perm_asig.view_edit_for_puestos(["choferes"])
        assert "personal" in view
        assert "personal" in edit
        assert "planificacion" in view
        assert "planificacion" not in edit
        pending = {r["key"] for r in perm_asig.new_unassigned_resources()}
        assert "personal" not in pending


def test_admin_perfiles_page(auth_client):
    r = auth_client.get("/admin/perfiles")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Por puesto" in html
    assert "Por persona" in html
    assert "Comunes a todos" in html


def test_admin_can_save_puesto_permissions(auth_client, app):
    r = auth_client.get("/admin/perfiles")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    data = {
        "csrf_token": m.group(1),
        "puesto_id": "choferes",
        "permv_planificacion": "1",
        "perme_planificacion": "1",
        "permv_entregas": "1",
        "perme_entregas": "1",
    }
    r2 = auth_client.post("/admin/perfiles/puesto", data=data, follow_redirects=True)
    body = r2.get_data(as_text=True)
    assert r2.status_code == 200
    assert "error interno" not in body.lower()
    assert "guardados" in body.lower()
    with app.app_context():
        view, edit = perm_asig.view_edit_for_puestos(["choferes"])
        assert "planificacion" in view
        assert "entregas" in edit


def test_persona_override_on_perfiles_page(auth_client, app):
    with app.app_context():
        u = User(
            username="pytest_perfil_persona",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add(u)
        db.session.commit()
        uid = u.id

    r = auth_client.get(f"/admin/perfiles?ambito=persona&user_id={uid}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    data = {
        "csrf_token": m.group(1),
        "permv_personal": "1",
        "perme_personal": "1",
    }
    for key in PERMISSION_KEYS:
        if key in ("produccion", "salmuera"):
            data[f"permv_{key}"] = "1"
            data[f"perme_{key}"] = "1"
    r2 = auth_client.post(f"/admin/perfiles/persona/{uid}", data=data, follow_redirects=True)
    assert r2.status_code == 200
    assert "Recursos de la persona guardados" in r2.get_data(as_text=True)
    with app.app_context():
        view, edit = perm_asig.effective_perm_lists_for_user(db.session.get(User, uid))
        assert "personal" in view
        assert "personal" in edit
        assert "produccion" in view


def test_comunes_apply_without_repeating_per_puesto(app):
    with app.app_context():
        perm_asig.ensure_schema()
        perm_asig.replace_puesto_permissions(
            perm_asig.PUESTO_COMUN_ID,
            {"manual": (True, True), "planificacion": (True, False)},
        )
        db.session.commit()
        cv, ce = perm_asig.comunes_perm_sets()
        assert "manual" in cv
        assert "manual" in ce
        assert "planificacion" in cv
        assert "planificacion" not in ce

        view_none, edit_none = perm_asig.view_edit_for_puestos([])
        assert "manual" in view_none
        assert "planificacion" in view_none

        view_ch, edit_ch = perm_asig.view_edit_for_puestos(["choferes"])
        assert "manual" in view_ch
        assert "manual" in edit_ch

        perm_asig.replace_puesto_permissions(
            "choferes",
            {
                "manual": (True, True),
                "planificacion": (True, False),
                "entregas": (True, True),
            },
        )
        db.session.commit()
        own_v, own_e = perm_asig.puesto_own_perm_sets("choferes")
        assert "manual" not in own_v
        assert "planificacion" not in own_v
        assert "entregas" in own_v
        assert "entregas" in own_e
        combined_v, combined_e = perm_asig.view_edit_for_puestos(["choferes"])
        assert "manual" in combined_v
        assert "entregas" in combined_e


def test_grant_puesto_is_additive(app):
    with app.app_context():
        perm_asig.ensure_schema()
        perm_asig.replace_puesto_permissions("choferes", {"entregas": (True, True)})
        db.session.commit()
        assert perm_asig.grant_puesto_permissions("choferes", {"planificacion": (True, False)})
        db.session.commit()
        own_v, own_e = perm_asig.puesto_own_perm_sets("choferes")
        assert "entregas" in own_v
        assert "planificacion" in own_v
        assert "planificacion" not in own_e
        assert not perm_asig.grant_puesto_permissions("choferes", {"entregas": (True, True)})


def test_admin_bulk_sumar_puestos(auth_client, app):
    r = auth_client.get("/admin/perfiles")
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    data = {
        "csrf_token": m.group(1),
        "puesto_id": "__comun__",
        "puesto_ids": ["choferes", "operarios_planta"],
        "permv_recepcion": "1",
        "perme_recepcion": "1",
    }
    r2 = auth_client.post("/admin/perfiles/puestos/sumar", data=data, follow_redirects=True)
    assert r2.status_code == 200
    assert "Se sumaron los recursos tildados" in r2.get_data(as_text=True)
    with app.app_context():
        v1, e1 = perm_asig.puesto_own_perm_sets("choferes")
        v2, e2 = perm_asig.puesto_own_perm_sets("operarios_planta")
        assert "recepcion" in v1
        assert "recepcion" in e2


def test_admin_bulk_sumar_personas(auth_client, app):
    with app.app_context():
        u1 = User(
            username="pytest_bulk_a",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        u2 = User(
            username="pytest_bulk_b",
            password_hash=generate_password_hash("x"),
            is_admin=False,
            activo=True,
            rol=ROLE_OPERACIONES,
        )
        db.session.add_all([u1, u2])
        db.session.commit()
        id1, id2 = u1.id, u2.id

    r = auth_client.get(f"/admin/perfiles?ambito=persona&user_id={id1}")
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    data = {
        "csrf_token": m.group(1),
        "user_id": str(id1),
        "user_ids": [str(id1), str(id2)],
        "permv_personal": "1",
        "perme_personal": "1",
    }
    r2 = auth_client.post("/admin/perfiles/personas/sumar", data=data, follow_redirects=True)
    assert r2.status_code == 200
    assert "Se sumaron los recursos tildados" in r2.get_data(as_text=True)
    with app.app_context():
        v1, e1 = perm_asig.effective_perm_lists_for_user(db.session.get(User, id1))
        v2, e2 = perm_asig.effective_perm_lists_for_user(db.session.get(User, id2))
        assert "personal" in v1
        assert "personal" in e2


def test_admin_can_save_common_permissions(auth_client, app):
    r = auth_client.get("/admin/perfiles?ambito=puesto&puesto=__comun__")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m is not None
    data = {
        "csrf_token": m.group(1),
        "puesto_id": "__comun__",
        "permv_manual": "1",
        "perme_manual": "1",
    }
    r2 = auth_client.post("/admin/perfiles/puesto", data=data, follow_redirects=True)
    body = r2.get_data(as_text=True)
    assert r2.status_code == 200
    assert "Recursos comunes guardados" in body
    with app.app_context():
        view, edit = perm_asig.view_edit_for_puestos(["operarios_planta"])
        assert "manual" in view
        assert "manual" in edit
