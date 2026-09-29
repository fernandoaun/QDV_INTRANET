from __future__ import annotations

import io
import re
import zipfile

import pytest
from werkzeug.security import generate_password_hash

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _pptx(proceso="Proceso Logística test", responsable="Responsable: Jefe test") -> bytes:
    """Ficha con la misma estructura que la plantilla del registro (datos ficticios)."""

    def paras(*ts):
        return "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in ts)

    def tabla(titulo, *ts):
        return (
            f'<p:graphicFrame><a:graphic><a:graphicData><a:tbl>'
            f"<a:tr><a:tc><a:txBody>{paras(titulo)}</a:txBody></a:tc></a:tr>"
            f"<a:tr><a:tc><a:txBody>{paras(*ts)}</a:txBody></a:tc></a:tr>"
            f"</a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
        )

    cuerpo = (
        tabla("ENTRADAS", "Pedido A.", "Pedido B.")
        + tabla("¿CÓMO?", "Procedimiento X.")
        + tabla("SALIDAS", "Entrega hecha.")
        + tabla("INDICADORES", "Entregas en plazo (%).")
        + tabla("¿CON QUIÉN?", "Clientes.")
        + tabla("¿CON QUÉ?", "Camiones.", "Software QDV.")
        + f"<p:sp><p:txBody>{paras(proceso, responsable, 'Preparar pedidos.', 'Despachar.')}</p:txBody></p:sp>"
        + f"<p:sp><p:txBody>{paras('Fecha de actualización: 25/08/2026')}</p:txBody></p:sp>"
    )
    xml = f'<p:sld xmlns:a="{A}" xmlns:p="{P}"><p:cSld><p:spTree>{cuerpo}</p:spTree></p:cSld></p:sld>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ppt/slides/slide1.xml", xml)
    buf.seek(0)
    return buf


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-fichas"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-fichas", "csrf_token": tok}).status_code in (302, 303)
    return client


def test_leer_pptx_de_la_plantilla(app):
    from datetime import date

    from app.services import fichas_proceso_service as svc

    data, err = svc.leer_pptx(_pptx())
    assert err is None
    assert data["proceso"] == "Logística test" and data["responsable"] == "Jefe test"
    assert data["actividades"] == ["Preparar pedidos.", "Despachar."]
    assert data["entradas"] == ["Pedido A.", "Pedido B."] and data["con_que"] == ["Camiones.", "Software QDV."]
    assert data["fecha_actualizacion"] == date(2026, 8, 25)
    assert svc.leer_pptx(io.BytesIO(b"no es pptx"))[1]


@pytest.fixture
def ficha_id(app):
    from app.extensions import db
    from app.services import fichas_proceso_service as svc

    with app.app_context():
        data, _ = svc.leer_pptx(_pptx())
        f, errs = svc.crear(data, None, fecha_actualizacion=data["fecha_actualizacion"])
        assert not errs
        db.session.commit()
        return f.id


def test_listado_ficha_y_en_blanco(app, client, ficha_id):
    c = _login(app, client, "pytest_fichas_admin", is_admin=True, rol="operaciones")
    listado = c.get("/sgi/fichas-proceso/").get_data(as_text=True)
    assert "Logística test" in listado and "Jefe test" in listado and "Nueva ficha" in listado

    html = c.get(f"/sgi/fichas-proceso/{ficha_id}").get_data(as_text=True)
    for txt in ("FICHA DE PROCESO", "QDV-RG-PG-09_03", "Proceso Logística test", "Responsable: Jefe test",
                "¿CON QUÉ?", "ENTRADAS", "¿CÓMO?", "¿CON QUIÉN?", "SALIDAS", "INDICADORES", "Camiones.", "25/08/2026"):
        assert txt in html, txt

    blanco = c.get("/sgi/fichas-proceso/en-blanco").get_data(as_text=True)
    assert "FICHA DE PROCESO" in blanco and "QDV-RG-PG-09_03" in blanco and "ENTRADAS" in blanco
    assert "Logística test" not in blanco and "Camiones." not in blanco and "Editar" not in blanco


def test_sgi_edita_campos_y_queda_historial(app, client, ficha_id):
    c = _login(app, client, "pytest_fichas_sgi", is_admin=False, rol="sgi")
    assert 'name="entradas"' in c.get(f"/sgi/fichas-proceso/{ficha_id}?editar=1").get_data(as_text=True)
    r = c.post(
        f"/sgi/fichas-proceso/{ficha_id}",
        data={"proceso": "Logística test", "responsable": "Jefe de logística", "actividades": "Preparar pedidos.\n\nDespachar.\nFacturar.",
              "entradas": "Pedido A.", "salidas": "Entrega hecha.", "como": "Procedimiento X.", "con_que": "Camiones.",
              "con_quien": "Clientes.\nChoferes.", "indicadores": "Entregas en plazo (%)."},
    )
    assert r.status_code in (302, 303)
    from app.services import fichas_proceso_service as svc

    with app.app_context():
        f = svc.get(ficha_id)
        assert f.responsable == "Jefe de logística" and svc.items(f.actividades) == ["Preparar pedidos.", "Despachar.", "Facturar."]
        assert svc.items(f.con_quien) == ["Clientes.", "Choferes."]
        assert {x.campo for x in svc.cambios(f)} >= {"responsable", "actividades", "entradas", "con_quien"}
    hist = c.get(f"/sgi/fichas-proceso/{ficha_id}?historial=1").get_data(as_text=True)
    assert "Historial de cambios" in hist and "Jefe de logística" in hist
    # Alta y baja son del administrador.
    c.post(f"/sgi/fichas-proceso/{ficha_id}/baja")
    with app.app_context():
        assert svc.get(ficha_id) is not None
    assert c.get("/sgi/fichas-proceso/nueva", follow_redirects=False).status_code in (302, 303)


def test_admin_crea_y_da_de_baja(app, client):
    c = _login(app, client, "pytest_fichas_admin2", is_admin=True, rol="operaciones")
    r = c.post("/sgi/fichas-proceso/nueva", data={"proceso": "Mantenimiento test", "responsable": "Jefe mant.", "actividades": "Reparar."})
    assert r.status_code in (302, 303)
    fid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    assert c.post("/sgi/fichas-proceso/nueva", data={"proceso": ""}).status_code == 200
    c.post(f"/sgi/fichas-proceso/{fid}/baja")
    assert c.get(f"/sgi/fichas-proceso/{fid}").status_code == 404
    assert ">Mantenimiento test</a>" not in c.get("/sgi/fichas-proceso/").get_data(as_text=True)


def test_sin_acceso_sgi(app, client, ficha_id):
    c = _login(app, client, "pytest_fichas_oper", is_admin=False, rol="operaciones")
    assert c.get("/sgi/fichas-proceso/", follow_redirects=False).status_code in (302, 303)
    assert c.post(f"/sgi/fichas-proceso/{ficha_id}", data={"proceso": "X"}).status_code in (302, 303)


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        links = proc.registro_modulo_links("fichas_proceso")
    assert links == {"label": "Fichas de proceso", "blank_url": "/sgi/fichas-proceso/en-blanco", "filled_url": "/sgi/fichas-proceso/"}
