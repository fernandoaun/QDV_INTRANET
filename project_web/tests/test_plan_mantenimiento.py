from __future__ import annotations

from datetime import date

from tests.test_planificacion_module import planif_client, planif_user  # noqa: F401  (fixtures)


def _plan(app, **kw):
    from app.extensions import db
    from app.models import Equipo, MaintenancePlan

    with app.app_context():
        eq = Equipo(nombre_equipo="Bomba Pytest", descripcion="", area_sector="Salmuera", created_at_iso="2026-01-01T00:00:00")
        db.session.add(eq)
        db.session.flush()
        p = MaintenancePlan(
            equipo_id=eq.id, nombre="Cambio de sellos", tipo_mantenimiento="preventivo", responsable="Mantenimiento",
            created_at_iso="2026-01-01T00:00:00", updated_at_iso="2026-01-01T00:00:00", **kw,
        )
        db.session.add(p)
        db.session.commit()
        return int(p.id), int(eq.id)


def _orden(app, plan_id, equipo_id, fecha, estado):
    from app.extensions import db
    from app.models import MaintenanceOrder

    with app.app_context():
        db.session.add(MaintenanceOrder(plan_id=plan_id, equipo_id=equipo_id, fecha_programada=fecha, estado=estado,
                                        created_at_iso="2026-01-01T00:00:00", updated_at_iso="2026-01-01T00:00:00"))
        db.session.commit()


def test_plan_anual_ordenes_y_previstas(app):
    from app.services import plan_mantenimiento_service as pms

    pid, eid = _plan(app, frecuencia_periodo="trimestral", proxima_fecha="2026-02-10")
    _orden(app, pid, eid, "2026-02-10", "finalizado")
    _orden(app, pid, eid, "2026-05-10", "programado")
    with app.app_context():
        (fila,) = pms.plan_anual(2026, today=date(2026, 6, 1))
        assert fila.activo == "Bomba Pytest" and fila.ubicacion == "Salmuera" and fila.frecuencia == "Trimestral"
        estados = {i + 1: [(m.fecha.day, m.estado) for m in ms] for i, ms in enumerate(fila.meses) if ms}
        # Febrero hecho; mayo con orden vencida (ya pasó); agosto y noviembre previstos por la frecuencia.
        assert estados == {2: [(10, "hecho")], 5: [(10, "vencido")], 8: [(10, "previsto")], 11: [(10, "previsto")]}
        assert fila.n_ordenes == 2
        assert pms.plan_anual(2025, today=date(2026, 6, 1))[0].meses == [[] for _ in range(12)]


def test_frecuencia_en_dias_y_fin_de_mes(app):
    from app.services import plan_mantenimiento_service as pms

    _plan(app, frecuencia_dias=45, proxima_fecha="2026-11-01")
    with app.app_context():
        (fila,) = pms.plan_anual(2026, today=date(2026, 1, 1))
        assert [(i + 1, m[0].fecha.day) for i, m in enumerate(fila.meses) if m] == [(11, 1), (12, 16)]
    assert pms._sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_pantalla_y_en_blanco(app, planif_client):  # noqa: F811
    _plan(app, frecuencia_periodo="mensual", proxima_fecha=f"{date.today().year}-01-15")
    html = planif_client.get("/planificacion/plan-mantenimiento").get_data(as_text=True)
    for txt in ("Plan de mantenimiento", "QDV-RG-PO-01_01", "Bomba Pytest", "Salmuera", "Mensual", "Registro asociado",
                "PLAN DE MANTENIMIENTO", "Fecha de vigencia", "Rev. 00", "Página 1 de 1", "Control de cambios", "Confección del formulario"):
        assert txt in html, txt
    blanco = planif_client.get("/planificacion/plan-mantenimiento/en-blanco").get_data(as_text=True)
    assert "QDV-RG-PO-01_01" in blanco and "Confección del formulario" in blanco and "Bomba Pytest" not in blanco
    assert "Plan de mantenimiento" in planif_client.get("/planificacion/").get_data(as_text=True)


def test_registro_sgi(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        links = proc.registro_modulo_links("plan_mantenimiento")
    assert links == {"label": "Plan de mantenimiento", "blank_url": "/planificacion/plan-mantenimiento/en-blanco",
                     "filled_url": "/planificacion/plan-mantenimiento"}


def test_registros_del_modulo_mantenimiento(app):
    from app.services import sgi_procedimiento_service as proc

    with app.app_context():
        assert proc.registro_modulo_links("mant_fallas") == {
            "label": "Reporte de fallas", "blank_url": "/mantenimiento/reportar-falla", "filled_url": "/mantenimiento/correctivos"}
        for clave in ("mant_ordenes", "mant_equipos", "mant_recursos", "mant_predictivo"):
            assert proc.registro_modulo_links(clave)["filled_url"].startswith("/mantenimiento/"), clave
