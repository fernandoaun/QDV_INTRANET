"""Difusión por correo: digests al ganar cobertura y mail al aprobar."""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import EmpleadoPersonal, PermisoUsuario, User
from app.services import sgi_difusion_mail_service as difusion_svc
from app.services import sgi_documento_perfil_service as perfil_svc
from app.services import sgi_procedimiento_service as proc_svc
from app.user_roles import ROLE_OPERACIONES


@pytest.fixture
def sgi_editor(app):
    with app.app_context():
        u = User(
            username="pytest_dif_editor",
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


def _approve_doc(editor_id: int, perfiles: list[str], titulo: str = "DIFUSION"):
    doc, rev, _ = proc_svc.create_procedimiento_visual("PG", editor_id, "T", titulo=titulo)
    perfil_svc.sync_perfiles_documento(doc.id, perfiles)
    rev.reviso = "R"
    rev.revisor_correo = "revisor@example.com"
    rev.aprobo = "A"
    rev.aprobador_correo = "aprobador@example.com"
    db.session.commit()
    proc_svc.enviar_a_revision(rev.id, editor_id, "T")
    proc_svc.marcar_como_revisado(rev.id, editor_id, "T")
    return doc, rev


def test_documentos_vigentes_para_usuario_por_rol(app, sgi_editor, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            "app.services.sgi_difusion_mail_service.is_mail_fully_configured",
            lambda _app: True,
        )
        sent: list[dict] = []

        def _fake_mail(_app, **kwargs):
            sent.append(kwargs)

        monkeypatch.setattr("app.services.sgi_difusion_mail_service.enviar_mail", _fake_mail)

        op = User(
            username="pytest_dif_op",
            password_hash=generate_password_hash("x"),
            rol=ROLE_OPERACIONES,
            activo=True,
            nombre_completo="Operario Test",
        )
        other = User(
            username="pytest_dif_mant",
            password_hash=generate_password_hash("x"),
            rol="mantenimiento",
            activo=True,
        )
        db.session.add_all([op, other])
        db.session.flush()
        db.session.add(
            EmpleadoPersonal(
                user_id=op.id,
                legajo="DIF-OP-01",
                apellido="Test",
                nombre="Operario",
                email="op@example.com",
                fecha_ingreso=__import__("datetime").date(2024, 1, 1),
                estado="activo",
            )
        )
        db.session.commit()

        doc, rev = _approve_doc(sgi_editor, [ROLE_OPERACIONES], titulo="MAIL APPROVE")
        # Aprobar dispara mail de aprobación (mockeado)
        ok, msg = proc_svc.aprobar_revision(rev.id, sgi_editor, "T")
        assert ok
        assert any(doc.codigo in (m.get("asunto") or "") for m in sent)
        assert any("op@example.com" in (m.get("destinatarios") or []) for m in sent)

        items = difusion_svc.documentos_vigentes_para_usuario(op)
        assert any(d.id == doc.id for d, _ in items)
        assert difusion_svc.documentos_vigentes_para_usuario(other) == []

        before = frozenset()
        assert difusion_svc.notify_usuario_si_cobertura_aumenta(app, op.id, before) is True
        digest_mails = [m for m in sent if "Documentos vigentes" in (m.get("asunto") or "")]
        assert digest_mails
        assert "Abrir documento" in (digest_mails[-1].get("cuerpo_html") or "")


def test_nuevos_perfiles_en_doc_aprobado_envia_digest(app, sgi_editor, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            "app.services.sgi_difusion_mail_service.is_mail_fully_configured",
            lambda _app: True,
        )
        sent: list[dict] = []
        monkeypatch.setattr(
            "app.services.sgi_difusion_mail_service.enviar_mail",
            lambda _app, **kwargs: sent.append(kwargs),
        )

        op = User(
            username="pytest_dif_op2",
            password_hash=generate_password_hash("x"),
            rol=ROLE_OPERACIONES,
            activo=True,
        )
        db.session.add(op)
        db.session.flush()
        db.session.add(
            EmpleadoPersonal(
                user_id=op.id,
                legajo="DIF-OP-02",
                apellido="Op",
                nombre="Dos",
                email="op2@example.com",
                fecha_ingreso=__import__("datetime").date(2024, 2, 1),
                estado="activo",
            )
        )
        db.session.commit()

        doc, rev = _approve_doc(sgi_editor, ["mantenimiento"], titulo="LUEGO OP")
        proc_svc.aprobar_revision(rev.id, sgi_editor, "T")
        sent.clear()

        # Doc ya aprobado: agregar perfil operaciones (como al editar carátula de otra rev)
        perfil_svc.sync_perfiles_documento(doc.id, ["mantenimiento", ROLE_OPERACIONES])
        db.session.commit()
        n = difusion_svc.notify_usuarios_por_nuevos_perfiles(app, doc, [ROLE_OPERACIONES])
        assert n >= 1
        assert any("op2@example.com" in (m.get("destinatarios") or []) for m in sent)
        assert any("Documentos vigentes" in (m.get("asunto") or "") for m in sent)


def test_cobertura_sin_aumento_no_reenvia(app, sgi_editor, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            "app.services.sgi_difusion_mail_service.is_mail_fully_configured",
            lambda _app: True,
        )
        sent: list = []
        monkeypatch.setattr(
            "app.services.sgi_difusion_mail_service.enviar_mail",
            lambda _app, **kwargs: sent.append(kwargs),
        )
        op = User(
            username="pytest_dif_op3",
            password_hash=generate_password_hash("x"),
            rol=ROLE_OPERACIONES,
            activo=True,
        )
        db.session.add(op)
        db.session.flush()
        db.session.add(
            EmpleadoPersonal(
                user_id=op.id,
                legajo="DIF-OP-03",
                apellido="Op",
                nombre="Tres",
                email="op3@example.com",
                fecha_ingreso=__import__("datetime").date(2024, 3, 1),
                estado="activo",
            )
        )
        db.session.commit()
        doc, rev = _approve_doc(sgi_editor, [ROLE_OPERACIONES], titulo="NO SPAM")
        proc_svc.aprobar_revision(rev.id, sgi_editor, "T")
        sent.clear()
        before = difusion_svc.coverage_doc_ids(op.id)
        assert before
        assert difusion_svc.notify_usuario_si_cobertura_aumenta(app, op.id, before) is False
        assert sent == []
