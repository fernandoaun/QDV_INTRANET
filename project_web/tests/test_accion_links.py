"""Links de acción de los avisos: se resuelve el trámite desde el celular, sin sesión."""
from __future__ import annotations

import re
from datetime import date, timedelta

import pytest


def _url(app, tipo, obj_id, **kw):
    from app.services import accion_link_service as accion_svc

    return "/accion/" + accion_svc.crear_token(app, tipo, obj_id, **kw)


def _admin(app):
    from app.extensions import db
    from app.models import EmpleadoPersonal, User
    from app.services import personal_service as ps

    ps.sync_empleados_from_users()
    admin = db.session.query(User).filter(User.username == "pytest_admin").one()
    emp = db.session.query(EmpleadoPersonal).filter(EmpleadoPersonal.user_id == admin.id).one()
    emp.email, emp.dni, emp.puesto = "admin@qdv.test", "30111000", "Gerente"
    db.session.commit()
    return admin, emp


def test_link_invalido_y_sin_sesion(app, client):
    assert "no es válido" in client.get("/accion/basura").get_data(as_text=True)


def test_sgi_revisar_y_devolver_desde_el_link(app, client, admin_user, monkeypatch):
    from app.extensions import db
    from app.services import accion_link_service as accion_svc
    from app.services import sgi_documento_perfil_service as perfil_svc
    from app.services import sgi_procedimiento_service as proc
    from app.services import sgi_workflow_service as wf

    enviados = []
    monkeypatch.setattr(wf, "is_mail_fully_configured", lambda app: True)
    monkeypatch.setattr(wf, "enviar_mail", lambda app, **kw: enviados.append(kw))
    monkeypatch.setattr(wf, "_pdf", lambda doc, rev: ("doc.pdf", b"%PDF-x", "application/pdf"))

    admin, _emp = _admin(app)
    doc, rev, err = proc.create_procedimiento_visual("PG", admin.id, "Tester", titulo="LINK SGI")
    assert err is None
    rev.reviso, rev.revisor_correo = "REVISOR", "admin@qdv.test"
    rev.aprobo, rev.aprobador_correo = "APROBADOR", "admin@qdv.test"
    perfil_svc.sync_perfiles_documento(doc.id, ["operaciones"])
    db.session.commit()
    assert proc.enviar_a_revision(rev.id, admin.id, "Tester")[0]
    (mail,) = enviados
    assert mail["destinatarios"] == ["admin@qdv.test"] and mail["adjuntos"][0][0] == "doc.pdf"
    link = re.search(r"/accion/[\w.\-]+", mail["cuerpo_texto"]).group(0)

    html = client.get(link).get_data(as_text=True)
    assert "Marcar como revisado" in html and "LINK SGI" in html
    assert client.get(link + "/documento.pdf").status_code in (200, 404)  # sin WeasyPrint en tests da 404
    html = client.post(link, data={"accion": "firmar"}).get_data(as_text=True)
    assert "Revisión registrada" in html
    db.session.refresh(rev)
    assert rev.estado == "revisado" and rev.fecha_revision == date.today()

    # Al aprobador le llega su link; devuelve con observaciones → vuelve a borrador.
    link_ap = re.search(r"/accion/[\w.\-]+", enviados[-1]["cuerpo_texto"]).group(0)
    assert accion_svc.leer_token(link_ap.split("/")[-1])[0]["t"] == accion_svc.SGI_APROBAR
    assert "Ya podés" not in client.post(link_ap, data={"accion": "devolver", "observaciones": ""}).get_data(as_text=True)
    html = client.post(link_ap, data={"accion": "devolver", "observaciones": "Falta el punto 5.3"}).get_data(as_text=True)
    assert "devuelto a borrador" in html
    db.session.refresh(rev)
    assert rev.estado == "borrador"
    assert "Falta el punto 5.3" in enviados[-1]["cuerpo_texto"]
    # El link ya no sirve para firmar.
    assert "ya no está pendiente" in client.get(link_ap).get_data(as_text=True)


def test_vacaciones_responsable_y_empleado(app, client, admin_user):
    from app.extensions import db
    from app.models import PersonalVacacion
    from app.services import accion_link_service as accion_svc
    from app.services import personal_service as ps

    admin, emp = _admin(app)
    ps.set_responsable_vacaciones(admin.id, by_user_id=admin.id)
    ps.save_vacacion_periodo({"empleado_id": str(emp.id), "anio": "2026", "dias_asignados": "14"}, user_id=admin.id)
    ok, _, vac = ps.solicitar_vacacion(emp.id, user_id=admin.id, data={"fecha_desde": "2026-07-01", "fecha_hasta": "2026-07-05", "anio": "2026"})
    assert ok
    link = _url(app, accion_svc.VAC_RESPONSABLE, vac.id, user_id=admin.id)
    assert "Proponer otras fechas" in client.get(link).get_data(as_text=True)
    html = client.post(link, data={"accion": "modificar", "fecha_desde": "2026-07-06", "fecha_hasta": "2026-07-08"}).get_data(as_text=True)
    assert "Propuesta enviada" in html
    vac = db.session.get(PersonalVacacion, vac.id)
    assert vac.estado == "modificada"

    link_emp = _url(app, accion_svc.VAC_EMPLEADO, vac.id, user_id=admin.id, emp=emp.id)
    assert "Acepto las nuevas fechas" in client.get(link_emp).get_data(as_text=True)
    client.post(link_emp, data={})
    assert db.session.get(PersonalVacacion, vac.id).estado == "aprobada"
    # Otro legajo en el token: no lo deja.
    assert "ya no existe" in client.get(_url(app, accion_svc.VAC_EMPLEADO, vac.id, emp=emp.id + 99)).get_data(as_text=True)


def test_epp_pedido_entregar_desde_el_link(app, client, admin_user):
    from app.extensions import db
    from app.models import PersonalEppItem, PersonalSolicitudEpp
    from app.services import accion_link_service as accion_svc
    from app.services import epp_pedidos_service as epp_ped_svc

    admin, emp = _admin(app)
    item = PersonalEppItem(nombre="Guantes link", categoria="epp", activo=True)
    db.session.add(item)
    db.session.commit()
    sol, err = epp_ped_svc.crear(emp, {"item_id": str(item.id), "motivo": "rotura", "cantidad": "2", "talle": "9"}, admin.id)
    assert err is None
    db.session.commit()
    link = _url(app, accion_svc.EPP_PEDIDO, sol.id, user_id=admin.id)
    assert "Registrar la entrega" in client.get(link).get_data(as_text=True)
    html = client.post(link, data={"accion": "entregar", "fecha": "2026-10-20", "cantidad": "2", "talle": "9",
                                   "tipo_modelo": "Nitrilo", "marca": "Ansell", "certificacion": "SI"}).get_data(as_text=True)
    assert "Entrega registrada" in html, html
    sol = db.session.get(PersonalSolicitudEpp, sol.id)
    assert sol.estado == "entregada" and sol.entrega_id


def test_vencimiento_renovar_desde_el_link(app, client, admin_user):
    from app.services import accion_link_service as accion_svc
    from app.services import vencimiento_service as vs

    admin, _ = _admin(app)
    ok, _ = vs.create_sector("Habilitaciones", "", admin.id)
    sector = vs.list_sectores()[0]
    v, err = vs.create_vencimiento(
        {"sector_id": str(sector.id), "nombre": "Matafuegos", "fecha_vencimiento": (date.today() + timedelta(days=10)).isoformat(),
         "responsable": "Mantenimiento", "email_aviso": "admin@qdv.test"}, admin.id, "Tester")
    assert v is not None, err
    link = _url(app, accion_svc.VENCIMIENTO, v.id, email="admin@qdv.test")
    assert "Registrar la renovación" in client.get(link).get_data(as_text=True)
    nueva = (date.today() + timedelta(days=375)).isoformat()
    html = client.post(link, data={"nueva_fecha": nueva}).get_data(as_text=True)
    assert "Renovación registrada" in html
    assert not vs.get_vencimiento(v.id).activo
    assert "Ya fue renovado" in client.get(link).get_data(as_text=True)


def test_tareas_cumplidas_desde_el_link(app, client, admin_user):
    from app.extensions import db
    from app.models import PlanificacionActividad
    from app.services import accion_link_service as accion_svc

    a = PlanificacionActividad(titulo="Calibrar balanza", fecha_inicio=date.today(), fecha_fin=date.today(), estado="pendiente")
    db.session.add(a)
    db.session.commit()
    link = _url(app, accion_svc.TAREAS, 0, email="x@qdv.test", p=[a.id], o=[])
    assert "Calibrar balanza" in client.get(link).get_data(as_text=True)
    assert "no es de este aviso" in client.post(link, data={"accion": f"act:{a.id + 1}"}).get_data(as_text=True)
    assert "quedó cumplida" in client.post(link, data={"accion": f"act:{a.id}"}).get_data(as_text=True)
    assert db.session.get(PlanificacionActividad, a.id).estado == "finalizada"


@pytest.mark.parametrize("modulo", ["vacaciones", "pedido_epp"])
def test_bot_pedidos_del_personal(app, admin_user, modulo):
    from app.extensions import db
    from app.models import PersonalEppItem, PersonalSolicitudEpp, PersonalVacacion
    from app.services import personal_service as ps
    from app.services import whatsapp_write_service as write_svc

    with app.test_request_context():
        admin, emp = _admin(app)
        if modulo == "vacaciones":
            ps.save_vacacion_periodo({"empleado_id": str(emp.id), "anio": "2026", "dias_asignados": "14"}, user_id=admin.id)
            with pytest.raises(ValueError, match="disponibles"):
                write_svc.preview_and_token(admin, modulo, {"desde": "2026-07-01", "hasta": "2026-07-30"}, "texto")
            payload = {"desde": "2026-07-01", "hasta": "2026-07-05"}
        else:
            db.session.add(PersonalEppItem(nombre="Botines de seguridad", categoria="ropa", activo=True))
            db.session.commit()
            with pytest.raises(ValueError, match="motivo|Por qué"):
                write_svc.preview_and_token(admin, modulo, {"item": "botines"}, "texto")
            payload = {"item": "botines", "cantidad": 1, "talle": "42", "motivo": "desgaste"}
        out = write_svc.preview_and_token(admin, modulo, payload, "texto")
        assert out["needs_confirm"]
        res = write_svc.confirm_and_save(admin, out["confirm_token"])
        assert res["ok"] and "enviad" in res["message"]
        if modulo == "vacaciones":
            assert db.session.query(PersonalVacacion).one().estado == "solicitada"
        else:
            assert db.session.query(PersonalSolicitudEpp).one().talle == "42"


def test_aviso_de_prueba_no_guarda_nada(app, client, admin_user):
    from app.extensions import db
    from app.models import PlanificacionActividad
    from app.services import accion_link_service as accion_svc

    a = PlanificacionActividad(titulo="Tarea demo", fecha_inicio=date.today(), fecha_fin=date.today(), estado="pendiente")
    db.session.add(a)
    db.session.commit()
    link = _url(app, accion_svc.TAREAS, 0, email="x@qdv.test", p=[a.id], o=[], demo=1)
    html = client.post(link, data={"accion": f"act:{a.id}"}).get_data(as_text=True)
    assert "No se guardó nada" in html
    assert db.session.get(PlanificacionActividad, a.id).estado == "pendiente"
    for tipo in (accion_svc.VAC_RESPONSABLE, accion_svc.VAC_EMPLEADO, accion_svc.EPP_PEDIDO):
        assert "(ejemplo)" in client.get(_url(app, tipo, 0, demo=1)).get_data(as_text=True) or tipo == accion_svc.VAC_EMPLEADO


def test_whatsapp_sin_links():
    from app.services.whatsapp_avisos_service import armar_texto

    t = armar_texto("Aviso", "Vence algo.\nVer en el sistema: https://x.ar/a/1\nAprobar o rechazar (desde el celular, sin entrar al sistema): https://x.ar/accion/abc\nFin")
    assert "http" not in t and "Ver en el sistema" not in t and "Fin" in t and "Vence algo." in t


def test_responder_por_whatsapp(app, admin_user):
    from app.extensions import db
    from app.models import Vencimiento
    from app.services import vencimiento_service as vs
    from app.services import whatsapp_write_service as write_svc

    with app.test_request_context():
        admin, _ = _admin(app)
        vs.create_sector("Habilitaciones", "", admin.id)
        v, _ = vs.create_vencimiento(
            {"sector_id": str(vs.list_sectores()[0].id), "nombre": "Matafuegos", "fecha_vencimiento": (date.today() + timedelta(days=5)).isoformat(),
             "responsable": "Mant", "email_aviso": "admin@qdv.test"}, admin.id, "Tester")
        v.aviso_30_dias_enviado = True
        db.session.commit()
        from app.services import avisos_pendientes_service as pend_svc

        (p,) = [x for x in pend_svc.pendientes(admin) if x["tipo"] == "vencimiento"]
        with pytest.raises(ValueError, match="podés"):
            write_svc.preview_and_token(admin, "responder", {"pendiente": p["pendiente"], "accion": "aprobar"}, "texto")
        nueva = (date.today() + timedelta(days=370)).isoformat()
        out = write_svc.preview_and_token(admin, "responder", {"pendiente": p["pendiente"], "accion": "renovar", "campos": {"nueva_fecha": nueva}}, "texto")
        assert "Matafuegos" in out["resumen"]
        res = write_svc.confirm_and_save(admin, out["confirm_token"])
        assert res["ok"] and not db.session.get(Vencimiento, v.id).activo
        with pytest.raises(ValueError, match="ya no está pendiente"):
            write_svc.preview_and_token(admin, "responder", {"pendiente": p["pendiente"], "accion": "renovar"}, "texto")


def test_aviso_flujo_dice_si_salio_por_whatsapp(app, admin_user):
    from app.extensions import db
    from app.services import sgi_workflow_service as wf

    with app.test_request_context():
        admin, emp = _admin(app)
        admin.whatsapp_e164 = "+5492990000000"
        db.session.commit()
        msg = lambda d: wf.workflow_mail_status_message(app, mail_sent=True, rol="aprobador", destinatarios=d)  # noqa: E731
        assert msg(["admin@qdv.test"]) == "Se notificó al aprobador por correo y por WhatsApp."
        assert "por WhatsApp no, porque otro@x.ar" in msg(["otro@x.ar"])
        assert "a otro@x.ar solo por correo" in msg(["admin@qdv.test", "otro@x.ar"])
        assert wf.workflow_mail_status_message(app, mail_sent=True, rol="revisor") == "Se notificó al revisor por correo."
