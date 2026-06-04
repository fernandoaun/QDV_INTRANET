"""Flujo de revisión / aprobación de procedimientos SGI."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import PermisoUsuario, SgiNotificacion, User
from app.models.sgi import ESTADO_EN_REVISION, ESTADO_REVISADO
from app.services import sgi_notification_service as notif_svc
from app.services import sgi_procedimiento_service as proc_svc


@pytest.fixture
def sgi_editor(app):
    with app.app_context():
        u = User(
            username="pytest_sgi_wf_editor",
            password_hash=generate_password_hash("pw"),
            is_admin=False,
            rol="sgi",
            activo=True,
        )
        db.session.add(u)
        db.session.flush()
        db.session.add(
            PermisoUsuario(user_id=u.id, permiso="sgi_hub", habilitado=True, puede_editar=False)
        )
        db.session.add(
            PermisoUsuario(user_id=u.id, permiso="sgi_documentos_edit", habilitado=True, puede_editar=True)
        )
        db.session.commit()
        uid = u.id
        yield uid
        db.session.delete(u)
        db.session.commit()


def test_workflow_enviar_marcar_aprobar(app, sgi_editor):
    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="WF TEST")
        assert err is None and doc and rev

        rev.reviso = "Revisor Test"
        rev.revisor_correo = "revisor@example.com"
        rev.aprobo = "Aprobador Test"
        rev.aprobador_correo = "aprobador@example.com"
        db.session.commit()

        ok, msg = proc_svc.enviar_a_revision(rev.id, sgi_editor, "Tester")
        assert ok, msg
        db.session.refresh(rev)
        assert rev.estado == ESTADO_EN_REVISION

        ok, msg = proc_svc.marcar_como_revisado(rev.id, sgi_editor, "Tester")
        assert ok, msg
        db.session.refresh(rev)
        assert rev.estado == ESTADO_REVISADO

        ok, msg = proc_svc.aprobar_revision(rev.id, sgi_editor, "Tester")
        assert ok, msg
        db.session.refresh(rev)
        assert rev.estado == "aprobado"

        n = db.session.scalar(select(func.count()).select_from(SgiNotificacion))
        assert int(n or 0) >= 1


def test_aprobar_requires_revisado_state(app, sgi_editor):
    with app.app_context():
        _doc, rev, _ = proc_svc.create_procedimiento_visual("PO", sgi_editor, "Tester", titulo="WF PO")
        rev.reviso = "R"
        rev.aprobo = "A"
        db.session.commit()
        proc_svc.enviar_a_revision(rev.id, sgi_editor, "Tester")
        ok, msg = proc_svc.aprobar_revision(rev.id, sgi_editor, "Tester")
        assert not ok
        assert "revisado" in msg.lower()


def test_users_to_notify_respects_registro_roles(app, sgi_editor):
    with app.app_context():
        doc, rev, _ = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="NOTIF")
        rev.reviso = "R"
        rev.aprobo = "A"
        data = json.loads(rev.contenido_json)
        data["registros"] = [
            {
                "nombre": "R1",
                "usuarios": "operaciones",
                "quien_archiva": "",
                "como": "",
                "donde": "",
                "tiempo_guarda": "",
                "disposicion_final": "",
            }
        ]
        rev.contenido_json = json.dumps(data)
        proc_svc._sync_child_rows(rev, data)
        doc.estado = "aprobado"
        rev.estado = "aprobado"
        db.session.commit()

        op = User(
            username="pytest_sgi_wf_op",
            password_hash=generate_password_hash("x"),
            rol="operaciones",
            activo=True,
        )
        mant = User(
            username="pytest_sgi_wf_mant",
            password_hash=generate_password_hash("x"),
            rol="mantenimiento",
            activo=True,
        )
        db.session.add_all([op, mant])
        db.session.flush()
        db.session.add(PermisoUsuario(user_id=op.id, permiso="sgi_hub", habilitado=True, puede_editar=False))
        db.session.commit()

        users = notif_svc.users_to_notify_document_approved(doc, rev)
        roles = {u.rol for u in users}
        assert "operaciones" in roles
