from __future__ import annotations

from datetime import date, timedelta

from app.extensions import db
from app.models import DeadlineReminderSent, Equipo, MaintenanceOrder, PlanificacionActividad
from app.services.deadline_reminder_service import (
    DOMAIN_MANTENIMIENTO_ORDER,
    DOMAIN_PLANIFICACION,
    collect_mantenimiento_reminders,
    collect_planificacion_reminders,
)


def test_collect_planificacion_reminder_window(app):
    fd = date(2026, 6, 30)
    today = fd - timedelta(days=30)
    with app.app_context():
        row = PlanificacionActividad(
            titulo="Tarea A",
            fecha_inicio=today,
            fecha_fin=fd,
            estado="pendiente",
        )
        db.session.add(row)
        db.session.commit()
        aid = row.id

        found = collect_planificacion_reminders(today=today, days_before=30)
        assert len(found) == 1
        assert found[0].id == aid

        db.session.add(DeadlineReminderSent(domain=DOMAIN_PLANIFICACION, entity_id=aid))
        db.session.commit()
        assert collect_planificacion_reminders(today=today, days_before=30) == []


def test_collect_mantenimiento_reminder_window(app):
    fp = date(2026, 8, 15)
    today = fp - timedelta(days=30)
    with app.app_context():
        eq = Equipo(nombre_equipo="Bomba 1", descripcion="test", created_at_iso="2026-01-01T00:00:00")
        db.session.add(eq)
        db.session.flush()
        order = MaintenanceOrder(
            equipo_id=eq.id,
            fecha_programada=fp.isoformat(),
            tipo_mantenimiento="preventivo",
            estado="programado",
            created_at_iso="2026-01-01T00:00:00",
            updated_at_iso="2026-01-01T00:00:00",
        )
        db.session.add(order)
        db.session.commit()
        oid = order.id

        found = collect_mantenimiento_reminders(today=today, days_before=30)
        assert len(found) == 1
        assert found[0].id == oid

        db.session.add(DeadlineReminderSent(domain=DOMAIN_MANTENIMIENTO_ORDER, entity_id=oid))
        db.session.commit()
        assert collect_mantenimiento_reminders(today=today, days_before=30) == []


def test_outside_window_not_collected(app):
    fd = date(2026, 12, 31)
    today = fd - timedelta(days=31)
    with app.app_context():
        db.session.add(
            PlanificacionActividad(
                titulo="Lejos",
                fecha_inicio=today,
                fecha_fin=fd,
                estado="pendiente",
            )
        )
        db.session.commit()
        assert collect_planificacion_reminders(today=today, days_before=30) == []
