from __future__ import annotations


def _create_equipo(app):
    from app.extensions import db
    from app.models import Equipo

    with app.app_context():
        equipo = Equipo(
            codigo_interno="EQ-PY-01",
            nombre_equipo="Electrolizador Pytest",
            descripcion="Equipo de prueba",
            tipo_equipo="Electrolizador",
            area_sector="Planta",
            estado="operativo",
            activo=True,
            created_at_iso="2026-04-29T10:00:00",
        )
        db.session.add(equipo)
        db.session.commit()
        return int(equipo.id)


def test_mantenimiento_hub_ok(mant_client):
    r = mant_client.get("/mantenimiento/", follow_redirects=True)
    assert r.status_code == 200
    assert b"Mantenimiento" in r.data


def test_mantenimiento_component_correctivo_close_and_export(mant_client, app):
    from app.extensions import db
    from app.models import MaintenanceComponent, MaintenanceFailure

    equipo_id = _create_equipo(app)

    assert mant_client.get("/mantenimiento/equipos").status_code == 200
    assert mant_client.get(f"/mantenimiento/equipos/{equipo_id}").status_code == 200
    assert mant_client.get("/mantenimiento/reportar-falla").status_code == 200

    r = mant_client.post(
        f"/mantenimiento/equipos/{equipo_id}",
        data={
            "action": "component",
            "codigo_interno": "BOM-PY-01",
            "nombre": "Bomba de salmuera pytest",
            "tipo_componente": "Bomba",
            "estado": "operativo",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        component = db.session.query(MaintenanceComponent).filter_by(nombre="Bomba de salmuera pytest").one()
        component_id = int(component.id)

    r = mant_client.post(
        "/mantenimiento/reportar-falla",
        data={
            "detected_at_iso": "2026-04-29T08:30",
            "equipo_id": str(equipo_id),
            "component_id": str(component_id),
            "descripcion_falla": "Pérdida en sello mecánico",
            "sintoma_observado": "Goteo visible",
            "causa_probable": "Desgaste",
            "criticidad": "alta",
            "responsable_trabajo": "Mantenimiento",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        failure = db.session.query(MaintenanceFailure).filter_by(descripcion_falla="Pérdida en sello mecánico").one()
        failure_id = int(failure.id)
        assert failure.estado == "reportado"
        assert failure.component_id == component_id

    assert mant_client.get("/mantenimiento/correctivos").status_code == 200
    assert mant_client.get(f"/mantenimiento/correctivos/{failure_id}").status_code == 200

    r = mant_client.post(
        f"/mantenimiento/correctivos/{failure_id}",
        data={
            "estado": "finalizado",
            "criticidad": "alta",
            "descripcion_falla": "Pérdida en sello mecánico",
            "sintoma_observado": "Goteo visible",
            "causa_probable": "Desgaste",
            "causa_real": "Sello vencido",
            "accion_realizada": "Cambio de sello",
            "repuestos_utilizados": "Sello mecánico",
            "recursos_utilizados": "Mecánico",
            "responsable_trabajo": "Mantenimiento",
            "closed_at_iso": "2026-04-29T12:30",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        failure = db.session.get(MaintenanceFailure, failure_id)
        assert failure is not None
        assert failure.estado == "finalizado"
        assert failure.causa_real == "Sello vencido"
        assert failure.tiempo_fuera_servicio_horas == 4.0

    export = mant_client.get("/mantenimiento/correctivos/export.xlsx")
    assert export.status_code == 200
    assert export.data[:2] == b"PK"


def test_mantenimiento_preventivos_recursos_ordenes_y_predictivo(mant_client, app):
    from app.extensions import db
    from app.models import MaintenanceFailure, MaintenanceOrder, MaintenancePlan, MaintenancePrediction, MaintenanceResource

    equipo_id = _create_equipo(app)

    assert mant_client.get("/mantenimiento/preventivos").status_code == 200
    r = mant_client.post(
        "/mantenimiento/preventivos",
        data={
            "nombre": "Revisión mensual pytest",
            "equipo_id": str(equipo_id),
            "tipo_mantenimiento": "preventivo",
            "frecuencia_dias": "30",
            "proxima_fecha": "2026-05-10",
            "responsable": "Mantenimiento",
            "duracion_estimada_horas": "2",
            "tareas": "Control general",
            "repuestos_necesarios": "Juntas",
            "herramientas_necesarias": "Llaves",
            "epp_necesarios": "Guantes",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        plan = db.session.query(MaintenancePlan).filter_by(nombre="Revisión mensual pytest").one()
        plan_id = int(plan.id)

    assert mant_client.get(f"/mantenimiento/preventivos/{plan_id}").status_code == 200
    r = mant_client.post(
        "/mantenimiento/recursos",
        data={
            "equipo_id": str(equipo_id),
            "tipo_mantenimiento": "preventivo",
            "categoria": "repuesto",
            "nombre": "Junta pytest",
            "cantidad": "2",
            "unidad": "un",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.query(MaintenanceResource).filter_by(nombre="Junta pytest").count() == 1

    r = mant_client.post(
        f"/mantenimiento/preventivos/{plan_id}",
        data={"action": "program", "fecha_programada": "2026-05-09"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        order = db.session.query(MaintenanceOrder).filter_by(plan_id=plan_id).one()
        order_id = int(order.id)
        assert order.tipo_mantenimiento == "preventivo"
        assert len(order.order_resources) == 1

    assert mant_client.get("/mantenimiento/ordenes").status_code == 200
    assert mant_client.get(f"/mantenimiento/ordenes/{order_id}").status_code == 200
    r = mant_client.post(
        f"/mantenimiento/ordenes/{order_id}",
        data={
            "equipo_id": str(equipo_id),
            "tipo_mantenimiento": "preventivo",
            "fecha_programada": "2026-05-09",
            "prioridad": "media",
            "criticidad": "media",
            "estado": "finalizado",
            "responsable": "Mantenimiento",
            "tareas": "Control general",
            "resultado": "Sin novedades",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        order = db.session.get(MaintenanceOrder, order_id)
        assert order is not None
        assert order.estado == "finalizado"
        assert order.closed_at_iso is not None

    export = mant_client.get("/mantenimiento/ordenes/export.xlsx")
    assert export.status_code == 200
    assert export.data[:2] == b"PK"

    with app.app_context():
        for detected in ("2026-01-01T08:00:00", "2026-03-01T08:00:00", "2026-04-30T08:00:00"):
            db.session.add(
                MaintenanceFailure(
                    detected_at_iso=detected,
                    equipo_id=equipo_id,
                    reported_by_display="pytest",
                    descripcion_falla="Falla repetitiva pytest",
                    sintoma_observado="Vibración pytest",
                    causa_real="Desgaste pytest",
                    criticidad="media",
                    estado="finalizado",
                    closed_at_iso=detected,
                    created_at_iso=detected,
                    updated_at_iso=detected,
                )
            )
        db.session.commit()

    assert mant_client.get("/mantenimiento/predictivo").status_code == 200
    r = mant_client.post("/mantenimiento/predictivo", follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        prediction = db.session.query(MaintenancePrediction).filter_by(tipo_falla="Desgaste pytest").one()
        prediction_id = int(prediction.id)
        assert prediction.cantidad_fallas == 3
        assert prediction.fecha_estimada_proxima is not None

    r = mant_client.post(
        f"/mantenimiento/predictivo/{prediction_id}/programar",
        data={"fecha_programada": "2026-06-20"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        prediction = db.session.get(MaintenancePrediction, prediction_id)
        assert prediction is not None
        assert prediction.estado == "programada"
        assert db.session.query(MaintenanceOrder).filter_by(prediction_id=prediction_id, tipo_mantenimiento="predictivo").count() == 1
