"""Sectores aplicables y notificaciones por perfil en SGI."""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import PermisoUsuario, User
from app.services import sgi_documento_perfil_service as perfil_svc
from app.services import sgi_notification_service as notif_svc
from app.services import sgi_procedimiento_service as proc_svc
from app.user_roles import ROLE_OPERACIONES


@pytest.fixture
def sgi_editor(app):
    with app.app_context():
        u = User(
            username="pytest_perfil_editor",
            password_hash=generate_password_hash("pw"),
            is_admin=False,
            rol="sgi",
            activo=True,
        )
        db.session.add(u)
        db.session.flush()
        db.session.add(
            PermisoUsuario(user_id=u.id, permiso="sgi_documentos_edit", habilitado=True, puede_editar=True)
        )
        db.session.commit()
        yield u.id


def test_sync_and_notify_operaciones_only(app, sgi_editor):
    with app.app_context():
        op = User(
            username="pytest_perfil_op",
            password_hash=generate_password_hash("x"),
            rol=ROLE_OPERACIONES,
            activo=True,
        )
        mant = User(
            username="pytest_perfil_mant",
            password_hash=generate_password_hash("x"),
            rol="mantenimiento",
            activo=True,
        )
        db.session.add_all([op, mant])
        db.session.commit()

        doc, rev, _ = proc_svc.create_procedimiento_visual("PG", sgi_editor, "T", titulo="PERFIL TEST")
        perfil_svc.sync_perfiles_documento(doc.id, [ROLE_OPERACIONES])
        rev.reviso = "R"
        rev.revisor_correo = "revisor@example.com"
        rev.aprobo = "A"
        rev.aprobador_correo = "aprobador@example.com"
        db.session.commit()

        proc_svc.enviar_a_revision(rev.id, sgi_editor, "T")
        proc_svc.marcar_como_revisado(rev.id, sgi_editor, "T")
        proc_svc.aprobar_revision(rev.id, sgi_editor, "T")

        users = notif_svc.users_to_notify_document_approved(doc, rev)
        usernames = {u.username for u in users}
        assert "pytest_perfil_op" in usernames
        assert "pytest_perfil_mant" not in usernames

        assert proc_svc.documento_accesible_por_perfil(op, doc) is True
        assert proc_svc.documento_accesible_por_perfil(mant, doc) is False


def test_enviar_revision_requires_perfil(app, sgi_editor):
    with app.app_context():
        _doc, rev, _ = proc_svc.create_procedimiento_visual("PG", sgi_editor, "T", titulo="SIN PERFIL")
        rev.reviso = "R"
        db.session.commit()
        ok, msg = proc_svc.enviar_a_revision(rev.id, sgi_editor, "T")
        assert not ok
        assert "sector" in msg.lower() or "perfil" in msg.lower()
