"""
Regresión numérica de las fórmulas fijas de negocio (documentación ejecutable).
Implementación: app.services.shift_hypochlorite_indicators_service
"""


def test_ejemplo_caso1_produccion():
    """Caso 1: producción = final − inicial + cargas − ingresos admin."""
    stock_inicial = 20_000.0
    stock_final = 18_000.0
    cargas = 5_000.0
    ingresos_admin = 1_000.0
    produccion = stock_final - stock_inicial + cargas - ingresos_admin
    assert produccion == 2_000.0


def test_ejemplo_caso2_instantaneo():
    """Caso 2: instantáneo = inicial − cargas + ingresos admin."""
    stock_inicial = 15_000.0
    cargas = 3_000.0
    ingresos_admin = 2_000.0
    instant = stock_inicial - cargas + ingresos_admin
    assert instant == 14_000.0


def test_stock_instantaneo_descuenta_cargas_ya_entregadas(app):
    from app.extensions import db
    from app.models import Entrega, ShiftHandover, ShiftSession, User
    from app.services import shift_handover_service as sh
    from app.services.shift_hypochlorite_indicators_service import get_instant_stock

    with app.app_context():
        u = User(username="pytest_panel_stock", password_hash="x", is_admin=True, activo=True)
        db.session.add(u)
        db.session.flush()
        session = ShiftSession(
            user_id=int(u.id),
            effective_role="operaciones",
            started_at_iso="2026-04-28T08:00:00",
            ended_at_iso="2026-04-28T12:00:00",
            status="closed",
            created_at_iso="2026-04-28T08:00:00",
            updated_at_iso="2026-04-28T12:00:00",
        )
        db.session.add(session)
        db.session.flush()
        db.session.add(
            ShiftHandover(
                shift_session_id=int(session.id),
                outgoing_user_id=int(u.id),
                shift_started_at_iso="2026-04-28T08:00:00",
                handed_over_at_iso="2026-04-28T12:00:00",
                received_at_iso="2026-04-28T12:01:00",
                hypochlorite_stock_liters=10_000.0,
                status=sh.HANDOVER_RECEIVED,
                created_at_iso="2026-04-28T12:00:00",
                updated_at_iso="2026-04-28T12:01:00",
            )
        )
        db.session.add(
            Entrega(
                cliente="Cliente",
                lugar_entrega="Planta",
                producto="Hipoclorito",
                cantidad=1_500.0,
                unidad="L",
                fecha_prevista="2026-04-28",
                estado="entregada",
                created_at_iso="2026-04-28T12:10:00",
                updated_at_iso="2026-04-28T13:00:00",
                cargada_at_iso="2026-04-28T12:30:00",
                entregada_at_iso="2026-04-28T13:00:00",
            )
        )
        db.session.commit()

        assert get_instant_stock() == 8_500.0


def test_stock_instantaneo_usa_cantidad_real_cargada(app):
    from app.extensions import db
    from app.models import Entrega, ShiftHandover, ShiftSession, User
    from app.services import shift_handover_service as sh
    from app.services.shift_hypochlorite_indicators_service import get_instant_stock

    with app.app_context():
        u = User(username="pytest_panel_stock_real", password_hash="x", is_admin=True, activo=True)
        db.session.add(u)
        db.session.flush()
        session = ShiftSession(
            user_id=int(u.id),
            effective_role="operaciones",
            started_at_iso="2026-04-28T08:00:00",
            ended_at_iso="2026-04-28T12:00:00",
            status="closed",
            created_at_iso="2026-04-28T08:00:00",
            updated_at_iso="2026-04-28T12:00:00",
        )
        db.session.add(session)
        db.session.flush()
        db.session.add(
            ShiftHandover(
                shift_session_id=int(session.id),
                outgoing_user_id=int(u.id),
                shift_started_at_iso="2026-04-28T08:00:00",
                handed_over_at_iso="2026-04-28T12:00:00",
                received_at_iso="2026-04-28T12:01:00",
                hypochlorite_stock_liters=10_000.0,
                status=sh.HANDOVER_RECEIVED,
                created_at_iso="2026-04-28T12:00:00",
                updated_at_iso="2026-04-28T12:01:00",
            )
        )
        db.session.add(
            Entrega(
                cliente="Cliente",
                lugar_entrega="Planta",
                producto="Hipoclorito",
                cantidad=1_500.0,
                cantidad_programada=1_500.0,
                cantidad_real_cargada=1_200.0,
                unidad="L",
                fecha_prevista="2026-04-28",
                estado="cargada",
                created_at_iso="2026-04-28T12:10:00",
                updated_at_iso="2026-04-28T12:30:00",
                cargada_at_iso="2026-04-28T12:30:00",
            )
        )
        db.session.commit()

        assert get_instant_stock() == 8_800.0
