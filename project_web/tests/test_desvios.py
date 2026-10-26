from __future__ import annotations

import re
from datetime import date

import pytest
from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-dv"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-dv", "csrf_token": tok}).status_code in (302, 303)
    return client


@pytest.fixture
def desvio_id(app):
    from app.extensions import db
    from app.services import desvios_service as svc

    with app.app_context():
        d, errs = svc.crear(
            {"descripcion": "Lote con concentración fuera de especificación", "fecha": "10/10/2026", "clasificacion": "producto n.c.",
             "fuentes": ["Reclamo del cliente", "Inventado"], "encuadre": ["Prestación del servicio", "Gestión de servicio / PNC"],
             "causa_raiz": "Falla del dosificador.",
             "acciones_correctivas": [{"detalle": "Reemplazar dosificador", "responsable": "Mantenimiento", "fecha": "2026-11-01"}]},
            None,
        )
        assert not errs
        db.session.commit()
        assert d.numero == 1 and d.clasificacion == "Producto N.C." and svc.tipo(d) == "PNC" and d.estado == "Abierta"
        assert d.fuentes == "Reclamo del cliente" and d.encuadre == "Prestación del servicio\nGestión de servicio / PNC"
        return d.id


def test_hoja_listado_y_en_blanco(app, client, desvio_id):
    c = _login(app, client, "pytest_dv_admin", is_admin=True, rol="operaciones")
    html = c.get("/sgi/desvios/").get_data(as_text=True)
    for txt in ("QDV-RG-PG-08_01", "Lote con concentración", "10/10/2026", "PNC", "Abierta", "Nuevo reporte"):
        assert txt in html, txt
    hoja = c.get(f"/sgi/desvios/{desvio_id}").get_data(as_text=True)
    for txt in ("Registro de No conformidades, PNC y OM", "Encuadramiento en el SGC", "Gestión de residuos", "Acciones correctivas (AC)",
                "Reemplazar dosificador", "01/11/2026", "Verificación de la eficacia", "29/09/2026"):
        assert txt in hoja, txt
    blanco = c.get("/sgi/desvios/en-blanco").get_data(as_text=True)
    assert "Lote con concentración" not in blanco and "<input" not in blanco.split('class="dv-sheet"')[1]


def test_acciones_pasan_al_plan_y_seguimiento(app, client, desvio_id):
    from app.services import desvios_service as svc
    from app.services import plan_accion_service as plan

    c = _login(app, client, "pytest_dv_sgi", is_admin=False, rol="sgi")
    form = {"descripcion": "Lote con concentración fuera de especificación", "fecha": "10/10/2026", "clasificacion": "Producto N.C.",
            "causa_raiz": "Falla del dosificador.", "estado": "En proceso de cierre", "implementadas": "Sí", "fecha_implementacion": "05/11/2026",
            "acciones_inmediatas_filas": "1", "acciones_inmediatas_detalle_0": "Segregar el lote", "acciones_inmediatas_responsable_0": "Producción",
            "correcciones_filas": "1", "correcciones_detalle_0": "Reprocesar", "acciones_correctivas_filas": "2",
            "acciones_correctivas_detalle_0": "Reemplazar dosificador", "acciones_correctivas_responsable_0": "Mantenimiento",
            "acciones_correctivas_fecha_0": "01/11/2026", "cierre_filas": "1", "cierre_0": "Responsable SGC"}
    assert c.post(f"/sgi/desvios/{desvio_id}", data=form).status_code in (302, 303)
    c.post(f"/sgi/desvios/{desvio_id}", data=form)  # guardar otra vez no duplica en el plan
    with app.app_context():
        acciones = plan.listar()
        assert sorted(a.accion for a in acciones) == ["Reemplazar dosificador", "Segregar el lote"]  # «Reprocesar» no tiene responsable
        ac = next(a for a in acciones if a.accion == "Reemplazar dosificador")
        assert ac.tipo_accion == "Acción correctiva" and ac.tipo_hallazgo == "No Conformidad" and ac.origen == "Registro de NC, PNC y OM"
        assert ac.requisito == "QDV-RG-PG-08_01 Reporte N° 1" and ac.causa_raiz == "Aplica" and ac.fecha_cumplimiento == date(2026, 11, 1)
        d = svc.get(desvio_id)
        assert d.implementadas == "Sí" and d.cierre_responsables == "Responsable SGC" and d.estado == "En proceso de cierre"
        assert {x.campo for x in svc.cambios(d)} >= {"estado", "acciones_inmediatas", "implementadas"}
    assert c.post("/sgi/desvios/nueva", data={"descripcion": "Mejorar rotulado", "clasificacion": "Oportunidad de mejora",
                                              "estado": "Cerrada", "fecha": "12/10/2026"}).status_code in (302, 303)
    seg = c.get("/sgi/desvios/seguimiento").get_data(as_text=True)
    for txt in ("QDV-RG-PG-08_02", "Lote con concentración", "Mejorar rotulado", "RESUMEN CONSOLIDADO", "50 %", "Página 2 de 2"):
        assert txt in seg, txt
    with app.app_context():
        res = svc.resumen(svc.listar())
        assert res["por_tipo"]["PNC"]["En proceso de cierre"] == 1 and res["por_tipo"]["OM"]["Cerrada"] == 1 and res["pendientes"] == 1
    blanco = c.get("/sgi/desvios/seguimiento/en-blanco").get_data(as_text=True)
    assert "Mejorar rotulado" not in blanco and "RESUMEN CONSOLIDADO" in blanco
    assert c.post(f"/sgi/desvios/{desvio_id}", data={**form, "fecha": "40/10/2026", "estado": "Cerrada"}).status_code in (302, 303)
    with app.app_context():
        assert svc.get(desvio_id).estado == "En proceso de cierre"  # fecha inválida: no guarda nada


def test_sin_acceso_sgi(app, client, desvio_id):
    c = _login(app, client, "pytest_dv_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/desvios/", follow_redirects=False).status_code in (302, 303)
    assert c.get("/sgi/desvios/seguimiento", follow_redirects=False).status_code in (302, 303)


def test_admin_da_de_baja(app, client, desvio_id):
    c = _login(app, client, "pytest_dv_admin2", is_admin=True, rol="operaciones")
    c.post(f"/sgi/desvios/{desvio_id}/baja")
    assert c.get(f"/sgi/desvios/{desvio_id}").status_code == 404


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        assert proc.registro_modulo_links("desvios")["filled_url"] == "/sgi/desvios/"
        assert proc.registro_modulo_links("desvios_seguimiento") == {
            "label": "Seguimiento de PNC, NC y OM", "blank_url": "/sgi/desvios/seguimiento/en-blanco",
            "filled_url": "/sgi/desvios/seguimiento"}
