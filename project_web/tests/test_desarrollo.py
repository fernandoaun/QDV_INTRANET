from __future__ import annotations

import re

from werkzeug.security import generate_password_hash


def _login(app, client, username, **kw):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        db.session.add(User(username=username, password_hash=generate_password_hash("pw-dd"), activo=True, **kw))
        db.session.commit()
    tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    assert client.post("/login", data={"username": username, "password": "pw-dd", "csrf_token": tok}).status_code in (302, 303)
    return client


def _produccion(app):
    """Registros de salmuera y agua, e ingreso de sal, dentro del período de pruebas."""
    from app.extensions import db
    from app.models import AguaRegistro, IngresoStock, SalmueraRegistro

    with app.app_context():
        for i, (conc, soda) in enumerate(((104, 5.0), (120, 6.0), (98, 9.0))):
            db.session.add(SalmueraRegistro(
                fecha_iso="2026-11-05", hora_hm=f"1{i}:00", electrolizador=2, cantidad_celdas=10, turno="Mañana",
                voltajes_json="[]", voltaje_total=35.0, amperaje=1800.0, caudal_agua_l_h=1.0, caudal_salmuera_l_h=1.0,
                hipo_conc=conc, hipo_exceso_soda=soda, sal_temp=55.0, sal_conc=303.0, sal_ph=4.5, soda_conc=18.0, declor_ph=7.0, operador="Ibañez, Martin",
                lote="P26110501", created_at_iso="2026-11-05T10:00:00"))
        db.session.add(AguaRegistro(fecha_iso="2026-11-05", hora_hm="09:00", turno="Mañana", operador="Torres, Agustin",
                                    lote="P26110501", numero_columna=1, temperatura=20.0, dureza=0.0, created_at_iso="2026-11-05T09:00:00"))
        db.session.add(IngresoStock(categoria="materia_prima", producto="Sal Gruesa Lavada", marca="Salinas", vencimiento="05/11/2027",
                                    lote="S-55", cantidad=1000, unidad="kg", fecha="2026-11-05", hora="08:00", operador="X",
                                    created_at_iso="2026-11-05T08:00:00"))
        db.session.commit()


def test_desarrollo_toma_la_evidencia_y_pide_completar_antes_de_firmar(app, client):
    from app.services import desarrollo_service as svc

    _produccion(app)
    c = _login(app, client, "pytest_dd_admin", is_admin=True, rol="operaciones", nombre_completo="Aun, Silvio Fernando")
    assert "Fecha de inicio" in c.get("/sgi/desarrollos/nuevo").get_data(as_text=True)
    r = c.post("/sgi/desarrollos/nuevo", data={"fecha_inicio": "01/11/2026", "tipo": "Modificación",
                                               "producto_proceso": "Hipoclorito 100 g/L", "motivo": "Subir concentración",
                                               "prueba_desde": "04/11/2026", "prueba_hasta": "06/11/2026"})
    assert r.status_code in (302, 303)
    did = int(r.headers["Location"].split("/sgi/desarrollos/")[1].split("?")[0])
    hoja = c.get(f"/sgi/desarrollos/{did}").get_data(as_text=True)
    for txt in ("QDV-RG-PO-03_01", "QDV-RG-PO-03_02", "QDV-RG-PO-03_03", "Ibañez, Martin", "Sal Gruesa Lavada Salinas, lote S-55",
                "98 a 120 g/L", "1 fuera de especificación", "Lotes de producción P26110501", "dureza del agua 0",
                "Electrolizadores 2", "Para firmar la liberación falta completar"):
        assert txt in hoja, txt
    with app.app_context():
        ev = svc.evidencia(svc.get(did))
        assert ev["resultados"][0]["conforme"] is False and ev["resultados"][1]["conforme"] is False
    r = c.post(f"/sgi/desarrollos/{did}/firmar/planta", follow_redirects=True)
    assert "Antes de firmar completá" in r.get_data(as_text=True)

    form = {"fecha_inicio": "01/11/2026", "tipo": "Modificación", "producto_proceso": "Hipoclorito 100 g/L",
            "motivo": "Subir concentración", "prueba_desde": "04/11/2026", "prueba_hasta": "06/11/2026",
            "criterios": "Cloro activo ≥ 100 g/L", "resultado_final": "Se alcanza la concentración", "salidas_cumplen": "Sí",
            "verificacion_resultado": "Conforme", "requiere_validacion": "No", "justificacion": "Mismo uso previsto",
            "resultado_aprobacion": "APROBADO", "fecha_liberacion": "06/11/2026", "metodo_Ensayo de laboratorio": "1",
            "producto_0_conforme": "1", "recurso_materias_primas": "Sal, soda cáustica"}
    for i in range(7):
        form.update({f"etapa_{i}_responsable": "Aun", f"etapa_{i}_fecha_prevista": "05/11/2026",
                     f"etapa_{i}_fecha_realizada": "06/11/2026", f"etapa_{i}_estado": "Realizada"})
    for i in range(7):
        form[f"rev_{i}_conforme"] = "Sí"
    assert c.post(f"/sgi/desarrollos/{did}", data=form).status_code in (302, 303)
    with app.app_context():
        assert svc.faltantes(svc.get(did)) == []
    c.post(f"/sgi/desarrollos/{did}/firmar/planta")
    c.post(f"/sgi/desarrollos/{did}/firmar/calidad")
    with app.app_context():
        d = svc.get(did)
        assert set(svc.firmas(d)) == {"planta", "calidad"} and svc.estado(d) == "Liberado"
    c.post(f"/sgi/desarrollos/{did}", data={**form, "criterios": "Cloro activo ≥ 105 g/L"})
    with app.app_context():
        assert svc.firmas(svc.get(did)) == {}

    r = c.post(f"/sgi/desarrollos/{did}/cambios/nuevo", data={"fecha": "06/11/2026", "producto_proceso": "Hipoclorito",
                                                              "descripcion": "Cambio de proveedor de sal", "motivo": "Costo"})
    assert "marcá si afecta o no afecta a Materias primas" in r.get_data(as_text=True)
    cform = {"fecha": "06/11/2026", "producto_proceso": "Hipoclorito", "descripcion": "Cambio de proveedor de sal",
             "motivo": "Costo", "resultado": "Sí", **{f"control_{i}": "No" for i in range(4)},
             **{f"imp_{i}": "No afecta" for i in range(16)}, "imp_0": "Afecta", "imp_0_obs": "Otra sal"}
    r = c.post(f"/sgi/desarrollos/{did}/cambios/nuevo", data=cform)
    assert r.status_code in (302, 303)
    cid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    hoja = c.get(f"/sgi/desarrollos/cambios/{cid}").get_data(as_text=True)
    assert "QDV-RG-PO-03_04" in hoja and "Otra sal" in hoja and "Pendiente de firma" in hoja
    c.post(f"/sgi/desarrollos/cambios/{cid}/firmar/planta")
    assert "Firmado en el sistema por Aun, Silvio Fernando" in c.get(f"/sgi/desarrollos/cambios/{cid}").get_data(as_text=True)
    assert "Cambio de proveedor de sal" in c.get("/sgi/desarrollos/").get_data(as_text=True)


def test_registro_sgi_desarrollo(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        assert proc.registro_modulo_links("desarrollo_produccion")["filled_url"] == "/sgi/desarrollos/"
