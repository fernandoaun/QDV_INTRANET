"""Flujo de revisión / aprobación de procedimientos SGC."""
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
        op = User(
            username="pytest_wf_op_notif",
            password_hash=generate_password_hash("x"),
            rol="operaciones",
            activo=True,
        )
        db.session.add(op)
        db.session.commit()

        doc, rev, err = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="WF TEST")
        assert err is None and doc and rev

        from app.services import sgi_documento_perfil_service as perfil_svc

        rev.reviso = "Revisor Test"
        rev.revisor_correo = "revisor@example.com"
        rev.aprobo = "Aprobador Test"
        rev.aprobador_correo = "aprobador@example.com"
        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
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


def test_reenviar_aviso_revision(app, sgi_editor):
    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="REENVIO")
        assert err is None and doc and rev

        from app.services import sgi_documento_perfil_service as perfil_svc

        rev.reviso = "Revisor Test"
        rev.revisor_correo = "revisor@example.com"
        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
        db.session.commit()

        ok, msg = proc_svc.enviar_a_revision(rev.id, sgi_editor, "Tester")
        assert ok, msg
        db.session.refresh(rev)
        assert rev.estado == ESTADO_EN_REVISION

        ok, msg = proc_svc.reenviar_aviso_workflow(rev.id, {"revisor_correo": "revisor@example.com"})
        assert ok, msg
        assert "reenviado" in msg.lower()


def test_reenviar_avisos_pendientes_bulk(app, sgi_editor):
    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="BULK")
        assert err is None and doc and rev

        from app.services import sgi_documento_perfil_service as perfil_svc

        rev.reviso = "Revisor"
        rev.revisor_correo = "revisor@example.com"
        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
        db.session.commit()

        ok, _ = proc_svc.enviar_a_revision(rev.id, sgi_editor, "Tester")
        assert ok

        out = proc_svc.reenviar_avisos_pendientes(app, dry_run=True)
        assert out["total"] >= 1
        assert any(i.get("codigo") == doc.codigo for i in out["items"])


def test_aprobar_requires_revisado_state(app, sgi_editor):
    from app.services import sgi_documento_perfil_service as perfil_svc

    with app.app_context():
        doc, rev, _ = proc_svc.create_procedimiento_visual("PO", sgi_editor, "Tester", titulo="WF PO")
        rev.reviso = "R"
        rev.revisor_correo = "revisor@example.com"
        rev.aprobo = "A"
        rev.aprobador_correo = "aprobador@example.com"
        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
        db.session.commit()
        proc_svc.enviar_a_revision(rev.id, sgi_editor, "Tester")
        ok, msg = proc_svc.aprobar_revision(rev.id, sgi_editor, "Tester")
        assert not ok
        assert "revisado" in msg.lower()


def test_users_to_notify_uses_documento_perfiles(app, sgi_editor):
    from app.services import sgi_documento_perfil_service as perfil_svc

    with app.app_context():
        doc, rev, _ = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="NOTIF")
        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
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
        db.session.commit()

        users = notif_svc.users_to_notify_document_approved(doc, rev)
        usernames = {u.username for u in users}
        assert "pytest_sgi_wf_op" in usernames
        assert "pytest_sgi_wf_mant" not in usernames


def test_revisor_por_correo_legajo_puede_marcar_revisado(app, sgi_editor):
    from app.models import EmpleadoPersonal
    from app.services import sgi_documento_perfil_service as perfil_svc

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="CORREO WF")
        assert err is None and doc and rev

        revisor = User(
            username="pytest_sgi_wf_revisor",
            password_hash=generate_password_hash("x"),
            rol="operaciones",
            activo=True,
        )
        db.session.add(revisor)
        db.session.flush()
        db.session.add(
            EmpleadoPersonal(
                user_id=revisor.id,
                legajo="WF-REV-01",
                apellido="Revisor",
                nombre="Correo",
                email="revisor.correo@example.com",
            )
        )
        rev.reviso = "Otra persona"
        rev.revisor_correo = "revisor.correo@example.com"
        rev.aprobo = "Aprobador Test"
        rev.aprobador_correo = "aprobador@example.com"
        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
        db.session.commit()

        proc_svc.enviar_a_revision(rev.id, sgi_editor, "Tester")
        db.session.refresh(rev)
        assert proc_svc.user_can_marcar_revisado(revisor, rev)

        ok, msg = proc_svc.marcar_como_revisado(rev.id, revisor.id, "Revisor Correo")
        assert ok, msg
        db.session.refresh(rev)
        assert rev.estado == ESTADO_REVISADO


def test_revisor_y_aprobador_pueden_editar_contenido(app, sgi_editor):
    """Quien revisa (en_revision) y quien aprueba (revisado) pueden modificar el procedimiento."""
    from app.models import EmpleadoPersonal
    from app.services import sgi_documento_perfil_service as perfil_svc

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="EDIT WF")
        assert err is None and doc and rev

        revisor = User(
            username="pytest_sgi_wf_edit_rev",
            password_hash=generate_password_hash("x"),
            rol="operaciones",
            activo=True,
        )
        aprobador = User(
            username="pytest_sgi_wf_edit_apr",
            password_hash=generate_password_hash("x"),
            rol="operaciones",
            activo=True,
        )
        db.session.add_all([revisor, aprobador])
        db.session.flush()
        db.session.add_all(
            [
                EmpleadoPersonal(
                    user_id=revisor.id,
                    legajo="WF-EDIT-REV",
                    apellido="Revisor",
                    nombre="Edit",
                    email="revisor.edit@example.com",
                ),
                EmpleadoPersonal(
                    user_id=aprobador.id,
                    legajo="WF-EDIT-APR",
                    apellido="Aprobador",
                    nombre="Edit",
                    email="aprobador.edit@example.com",
                ),
            ]
        )
        rev.reviso = "Revisor Edit"
        rev.revisor_correo = "revisor.edit@example.com"
        rev.aprobo = "Aprobador Edit"
        rev.aprobador_correo = "aprobador.edit@example.com"
        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
        db.session.commit()

        ok, msg = proc_svc.enviar_a_revision(rev.id, sgi_editor, "Tester")
        assert ok, msg
        db.session.refresh(rev)
        assert rev.estado == ESTADO_EN_REVISION
        assert proc_svc.user_can_edit_revision_content(revisor, rev)
        assert not proc_svc.user_can_edit_revision_content(aprobador, rev)

        payload = proc_svc.revision_to_payload(rev)
        payload["titulo"] = "TITULO CORREGIDO POR REVISOR"
        payload["elaboro"] = rev.elaboro or ""
        payload["reviso"] = rev.reviso or ""
        payload["aprobo"] = rev.aprobo or ""
        payload["revisor_correo"] = rev.revisor_correo or ""
        payload["aprobador_correo"] = rev.aprobador_correo or ""
        payload["secciones"] = dict(payload.get("secciones") or {})
        payload["secciones"]["objeto"] = "<p>Cambio del revisor</p>"
        ok, msg, _ = proc_svc.save_revision_content(
            rev.id, payload, revisor.id, "Revisor Edit", actor=revisor
        )
        assert ok, msg
        db.session.refresh(doc)
        assert doc.titulo == "TITULO CORREGIDO POR REVISOR"

        ok, msg = proc_svc.marcar_como_revisado(rev.id, revisor.id, "Revisor Edit")
        assert ok, msg
        db.session.refresh(rev)
        assert rev.estado == ESTADO_REVISADO
        assert not proc_svc.user_can_edit_revision_content(revisor, rev)
        assert proc_svc.user_can_edit_revision_content(aprobador, rev)

        payload = proc_svc.revision_to_payload(rev)
        payload["titulo"] = "TITULO CORREGIDO POR APROBADOR"
        payload["elaboro"] = rev.elaboro or ""
        payload["reviso"] = rev.reviso or ""
        payload["aprobo"] = rev.aprobo or ""
        payload["revisor_correo"] = rev.revisor_correo or ""
        payload["aprobador_correo"] = rev.aprobador_correo or ""
        ok, msg, _ = proc_svc.save_revision_content(
            rev.id, payload, aprobador.id, "Aprobador Edit", actor=aprobador
        )
        assert ok, msg
        db.session.refresh(doc)
        assert doc.titulo == "TITULO CORREGIDO POR APROBADOR"

        db.session.delete(revisor)
        db.session.delete(aprobador)
        db.session.commit()


def test_angel_profile_can_aprobar_revision(app, sgi_editor):
    """Perfil Angel (solo lectura total) puede aprobar procedimientos en estado revisado."""
    from app.services import sgi_documento_perfil_service as perfil_svc
    from app.user_roles import ROLE_SOLO_LECTURA_TOTAL

    with app.app_context():
        angel = User(
            username="pytest_sgi_wf_angel",
            password_hash=generate_password_hash("x"),
            rol=ROLE_SOLO_LECTURA_TOTAL,
            activo=True,
        )
        db.session.add(angel)
        db.session.flush()

        doc, rev, _ = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="ANGEL WF")
        rev.reviso = "Revisor"
        rev.revisor_correo = "revisor@example.com"
        rev.aprobo = "Gerencia"
        rev.aprobador_correo = "gerencia@example.com"
        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
        db.session.commit()

        proc_svc.enviar_a_revision(rev.id, sgi_editor, "Tester")
        proc_svc.marcar_como_revisado(rev.id, sgi_editor, "Tester")
        db.session.refresh(rev)
        assert rev.estado == ESTADO_REVISADO

        assert proc_svc.user_can_aprobar_revision(angel, rev)
        assert not proc_svc.user_can_edit_revision_content(angel, rev)
        ok, msg = proc_svc.aprobar_revision(rev.id, angel.id, "Angel Test")
        assert ok, msg
        db.session.refresh(rev)
        assert rev.estado == "aprobado"

        db.session.delete(angel)
        db.session.commit()


def test_resolve_recipients_from_puesto_personal_email(app, sgi_editor, monkeypatch):
    """Los mails del flujo salen del legajo de quien ocupa el puesto del organigrama."""
    from app.models.personal import EmpleadoPersonal
    from app.services import sgi_workflow_service as wf_svc

    with app.app_context():
        holder = User(
            username="pytest_sgi_puesto_holder",
            password_hash=generate_password_hash("x"),
            rol="sgi",
            activo=True,
            nombre_completo="Silvano Puesto",
        )
        db.session.add(holder)
        db.session.flush()
        db.session.add(
            EmpleadoPersonal(
                user_id=holder.id,
                legajo="WF-PUESTO-01",
                apellido="Puesto",
                nombre="Silvano",
                email="silvano.puesto@example.com",
            )
        )
        doc, rev, err = proc_svc.create_procedimiento_visual("PG", sgi_editor, "Tester", titulo="PUESTO WF")
        assert err is None and doc and rev
        rev.reviso = "GERENCIA GENERAL"
        rev.revisor_correo = ""
        rev.aprobo = "GERENCIA GENERAL"
        rev.aprobador_correo = ""
        proc_svc.apply_puesto_fields_from_payload(
            rev,
            {
                "reviso_puesto_id": "gerencia_general",
                "aprobo_puesto_id": "gerencia_general",
            },
            sync_labels=False,
            sync_emails=False,
        )
        db.session.commit()

        monkeypatch.setattr(
            "app.services.sgi_anexo_service.organigrama_emails_for_puesto",
            lambda node_id: ["silvano.puesto@example.com"] if node_id == "gerencia_general" else [],
        )
        monkeypatch.setattr(
            "app.services.sgi_anexo_service.organigrama_puesto_holders",
            lambda node_id: (
                [{"user_id": holder.id, "nombre": "Silvano Puesto", "email": "silvano.puesto@example.com"}]
                if node_id == "gerencia_general"
                else []
            ),
        )

        recipients = wf_svc.resolve_revision_recipients(app, rev)
        assert recipients == ["silvano.puesto@example.com"]
        recipients_ap = wf_svc.resolve_approval_recipients(app, rev)
        assert recipients_ap == ["silvano.puesto@example.com"]

        from app.services import sgi_documento_perfil_service as perfil_svc

        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
        db.session.commit()
        ok, msg = proc_svc.enviar_a_revision(rev.id, sgi_editor, "Tester")
        assert ok, msg
        db.session.refresh(rev)
        assert rev.estado == ESTADO_EN_REVISION
        assert proc_svc.user_can_marcar_revisado(holder, rev)

        db.session.delete(holder)
        db.session.commit()

def test_msgi_workflow_firma_gerente_solo_tras_aprobar(auth_client, app, sgi_editor):
    """MSGC: mismo flujo que PG/PO; la imagen de firma del gerente solo aparece tras aprobar."""
    from io import BytesIO

    from app.services import sgi_documento_perfil_service as perfil_svc
    from werkzeug.datastructures import FileStorage

    with app.app_context():
        doc, rev, err = proc_svc.create_procedimiento_visual(
            "MSGC", sgi_editor, "Tester", titulo="MSGC FIRMA WF"
        )
        assert err is None and doc and rev
        rev.reviso = "Revisor Test"
        rev.revisor_correo = "revisor@example.com"
        rev.aprobo = "Aprobador Test"
        rev.aprobador_correo = "aprobador@example.com"
        perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
        db.session.commit()

        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        ok, msg = proc_svc.save_firma_gerente_file(
            doc.id,
            FileStorage(stream=BytesIO(png), filename="firma.png", content_type="image/png"),
            sgi_editor,
        )
        assert ok, msg
        assert proc_svc.firma_gerente_relative_path(doc.id) is not None

        doc_id, rev_id = doc.id, rev.id

        r_edit = auth_client.get(f"/sgi/msgc/procedimientos/{doc_id}/editor/{rev_id}")
        assert r_edit.status_code == 200
        html = r_edit.get_data(as_text=True)
        assert "Enviar a revisión" in html
        assert 'class="sgi-proc-firma-gerente"' not in html

        ok, msg = proc_svc.enviar_a_revision(rev_id, sgi_editor, "Tester")
        assert ok, msg
        ok, msg = proc_svc.marcar_como_revisado(rev_id, sgi_editor, "Tester")
        assert ok, msg
        ok, msg = proc_svc.aprobar_revision(rev_id, sgi_editor, "Tester")
        assert ok, msg

        r_vista = auth_client.get(f"/sgi/msgc/procedimientos/{doc_id}/vista/{rev_id}")
        assert r_vista.status_code == 200
        html_v = r_vista.get_data(as_text=True)
        assert 'class="sgi-proc-firma-gerente"' in html_v
        assert f"/sgi/msgc/{doc_id}/firma-gerente" in html_v

        doc_pg, rev_pg, _ = proc_svc.create_procedimiento_visual(
            "PG", sgi_editor, "Tester", titulo="PG SIN FIRMA"
        )
        rev_pg.estado = "aprobado"
        doc_pg.estado = "aprobado"
        db.session.commit()
        r_pg = auth_client.get(f"/sgi/pg/procedimientos/{doc_pg.id}/vista/{rev_pg.id}")
        assert r_pg.status_code == 200
        assert 'class="sgi-proc-firma-gerente"' not in r_pg.get_data(as_text=True)
