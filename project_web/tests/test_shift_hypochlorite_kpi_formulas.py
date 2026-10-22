"""
Regresión numérica de las fórmulas fijas de negocio (documentación ejecutable).
Implementación: app.services.shift_hypochlorite_indicators_service
"""
import pytest


@pytest.fixture(autouse=True)
def _sin_produccion_estimada(monkeypatch):
    """Estos tests validan la fórmula de cargas e ingresos; la producción estimada se prueba aparte."""
    from app.services import produccion_estimada_service as pe

    monkeypatch.setattr(pe, "estimar", lambda *a, **k: {"litros": 0.0, "detalle": {}, "config": pe.DEFAULTS | {"margen_carga_pct": 90.0}})


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


def test_ingreso_pt_de_cualquier_usuario_suma_al_panel(app):
    """El ingreso de hipoclorito terminado cuenta aunque lo cargue alguien que no es administrador."""
    from app.extensions import db
    from app.models import IngresoStock, User
    from app.services.shift_hypochlorite_indicators_service import sum_hipo_pt_ingresos_in_interval

    with app.app_context():
        u = User(username="pytest_ingreso_lab", password_hash="x", is_admin=False, rol="responsable_laboratorio", activo=True)
        db.session.add(u)
        db.session.flush()
        for prod, cant in (("Hipoclorito", 9_371.0), ("Cloro gaseoso", 500.0)):
            db.session.add(IngresoStock(categoria="producto_terminado", producto=prod, marca="QDV", vencimiento="", lote="", cantidad=cant, unidad="L",
                                        fecha="2026-10-20", hora="15:17", operador="Lab", cargado_por_user_id=int(u.id),
                                        created_at_iso="2026-10-20T15:17:00"))
        db.session.commit()
        assert sum_hipo_pt_ingresos_in_interval("2026-10-20T08:00:00", "2026-10-20T18:00:00") == 9_371.0
        assert sum_hipo_pt_ingresos_in_interval("2026-10-20T16:00:00", "2026-10-20T18:00:00") == 0.0


def test_ajuste_de_hipoclorito_va_al_panel_sin_lote(app):
    from app.services import stock_service as ss
    from app.services.shift_hypochlorite_indicators_service import sum_hipo_pt_ingresos_in_interval
    from app.utils.datetime_operacion import now_operacion_naive_local

    with app.app_context():
        ss.ensure_producto("producto_terminado", "Hipoclorito")
        datos = ss.load_stock_ajuste_view_data("producto_terminado", "Hipoclorito", "QDV")
        assert datos["ajuste_al_panel"] and datos["lotes"] == []
        rec = ss.save_ajuste_from_web_form(
            {"categoria": "producto_terminado", "producto": "Hipoclorito", "marca": "QDV", "tipo": "negativo",
             "cantidad": "1500", "motivo": "Recuento"}, operador="Test", admin_user_id=None)
        assert rec.ingreso_stock_id is None and rec.cantidad == -1500.0
        desde = now_operacion_naive_local().replace(hour=0, minute=0, second=0).isoformat(timespec="seconds")
        assert sum_hipo_pt_ingresos_in_interval(desde, None) == -1500.0
        # Los demás productos siguen pidiendo lote.
        ss.ensure_producto("materia_prima", "Sal")
        with pytest.raises(ValueError, match="lote"):
            ss.save_ajuste_from_web_form({"categoria": "materia_prima", "producto": "Sal", "marca": "X", "tipo": "positivo",
                                          "cantidad": "1", "motivo": "Recuento"}, operador="Test", admin_user_id=None)


def _turno_recibido_tarde(db, sh, username, *, corregido_informado=None):
    """Turno entregado a las 07:40 y recepcionado recién a las 16:11 con 9.500 L."""
    from app.models import ShiftHandover, ShiftSession, User

    u = User(username=username, password_hash="x", is_admin=True, activo=True)
    db.session.add(u)
    db.session.flush()
    session = ShiftSession(user_id=int(u.id), effective_role="operaciones", started_at_iso="2026-10-22T01:49:58",
                           ended_at_iso="2026-10-22T07:40:28", status="closed",
                           created_at_iso="2026-10-22T01:49:58", updated_at_iso="2026-10-22T07:40:28")
    db.session.add(session)
    db.session.flush()
    db.session.add(ShiftSession(user_id=int(u.id), effective_role="operaciones", started_at_iso="2026-10-22T16:11:17",
                                status="open", created_at_iso="2026-10-22T16:11:17", updated_at_iso="2026-10-22T16:11:17"))
    db.session.add(ShiftHandover(shift_session_id=int(session.id), outgoing_user_id=int(u.id),
                                 shift_started_at_iso="2026-10-22T01:49:58", handed_over_at_iso="2026-10-22T07:40:28",
                                 received_at_iso="2026-10-22T16:11:17", hypochlorite_stock_liters=9_500.0,
                                 hypochlorite_stock_liters_informado=corregido_informado,
                                 status=sh.HANDOVER_RECEIVED, created_at_iso="2026-10-22T07:40:28",
                                 updated_at_iso="2026-10-22T16:11:17"))
    return u


def _movimientos_entre_entrega_y_recepcion(db):
    from app.models import Entrega, IngresoStock

    db.session.add(Entrega(cliente="ARSA", lugar_entrega="Planta", producto="Hipoclorito", cantidad=1_250.0, unidad="L",
                           fecha_prevista="2026-10-22", estado="entregada", created_at_iso="2026-10-22T14:00:00",
                           updated_at_iso="2026-10-22T14:25:04", cargada_at_iso="2026-10-22T14:25:04"))
    db.session.add(IngresoStock(categoria="producto_terminado", producto="Hipoclorito", marca="QDV", vencimiento="-",
                                lote="L1", cantidad=19_700.0, unidad="L", fecha="2026-10-22", hora="14:56",
                                operador="Op", created_at_iso="2026-10-22T14:56:00"))


def test_stock_recibido_es_la_base_aunque_hubo_movimientos_antes(app, monkeypatch):
    """Lo que acepta el entrante al recibir es el stock a esa hora (regla de Fernando, 22/10/2026):
    cargas e ingresos anteriores a la recepción ya están reflejados en esa medición."""
    from app.extensions import db
    from app.services import shift_handover_service as sh
    from app.services.shift_hypochlorite_indicators_service import get_instant_stock

    monkeypatch.setattr(sh, "now_local_iso", lambda: "2026-10-22T18:00:00")
    with app.app_context():
        _turno_recibido_tarde(db, sh, "pytest_recibido_base")
        _movimientos_entre_entrega_y_recepcion(db)
        db.session.commit()
        assert get_instant_stock() == 9_500.0


def test_stock_corregido_al_recibir_cuenta_desde_la_recepcion(app, monkeypatch):
    """Si el entrante corrigió el stock al recibir, esa medición ya incluye lo anterior: no se cuenta dos veces."""
    from app.extensions import db
    from app.services import shift_handover_service as sh
    from app.services.shift_hypochlorite_indicators_service import get_instant_stock

    monkeypatch.setattr(sh, "now_local_iso", lambda: "2026-10-22T18:00:00")
    with app.app_context():
        _turno_recibido_tarde(db, sh, "pytest_hueco_corregido", corregido_informado=8_000.0)
        _movimientos_entre_entrega_y_recepcion(db)
        db.session.commit()
        assert get_instant_stock() == 9_500.0
