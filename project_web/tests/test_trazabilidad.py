"""Lote de despacho por carga y trazabilidad pulmón ⇄ lotes de materia prima."""
from datetime import date


def _usuario(db, User):
    u = User(username="pytest_traza", password_hash="x", is_admin=True, activo=True)
    db.session.add(u)
    db.session.flush()
    return u


def _cierre(db, u, desde, hasta, stock):
    from app.models import ShiftHandover, ShiftSession
    from app.services import shift_handover_service as sh

    s = ShiftSession(
        user_id=int(u.id), effective_role="operaciones", started_at_iso=desde, ended_at_iso=hasta,
        status="closed", created_at_iso=desde, updated_at_iso=hasta,
    )
    db.session.add(s)
    db.session.flush()
    db.session.add(
        ShiftHandover(
            shift_session_id=int(s.id), outgoing_user_id=int(u.id), shift_started_at_iso=desde,
            handed_over_at_iso=hasta, received_at_iso=hasta, hypochlorite_stock_liters=stock,
            status=sh.HANDOVER_RECEIVED, created_at_iso=hasta, updated_at_iso=hasta,
        )
    )


def _carga(db, cargada_at, litros, lote, cliente="Cliente", origen=None):
    from app.models import Entrega

    e = Entrega(
        cliente=cliente, lugar_entrega="Planta", producto="Hipoclorito", cantidad=litros, unidad="L",
        fecha_prevista=cargada_at[:10], estado="cargada", created_at_iso=cargada_at, updated_at_iso=cargada_at,
        cargada_at_iso=cargada_at, cantidad_real_cargada=litros, lote_despacho=lote,
        carga_origen_entrega_id=int(origen.id) if origen else None,
    )
    db.session.add(e)
    db.session.flush()
    return e


def _mp(db, producto, lote, fecha_ingreso, consumos):
    from app.models import ConsumoStock, IngresoStock

    ing = IngresoStock(
        categoria="materia_prima", producto=producto, marca="Prov", vencimiento="01/01/2028", lote=lote,
        cantidad=100, unidad="Bolsas", fecha=fecha_ingreso, hora="08:00", operador="x",
        created_at_iso=f"{fecha_ingreso}T08:00:00",
    )
    db.session.add(ing)
    db.session.flush()
    for f, h in consumos:
        db.session.add(
            ConsumoStock(
                categoria="materia_prima", producto=producto, marca="Prov", cantidad=1, fecha=f, hora=h,
                operador="x", ingreso_stock_id=int(ing.id), created_at_iso=f"{f}T{h}:00",
            )
        )
    db.session.flush()
    return ing


def _escenario(db, User):
    """Cuatro turnos de 8 h con stock de 1.000 L y 1.000 L producidos por turno (sin camiones)."""
    u = _usuario(db, User)
    cierres = ["2026-05-01T06:00:00", "2026-05-01T14:00:00", "2026-05-01T22:00:00", "2026-05-02T06:00:00", "2026-05-02T14:00:00"]
    stock = 1_000.0
    _cierre(db, u, "2026-04-30T22:00:00", cierres[0], stock)
    for desde, hasta in zip(cierres, cierres[1:]):
        stock += 1_000.0
        _cierre(db, u, desde, hasta, stock)
    return cierres


def test_lote_despacho_correlativo_por_dia(app):
    from app.extensions import db
    from app.services.entregas_service import siguiente_lote_despacho

    with app.app_context():
        assert siguiente_lote_despacho(date(2026, 10, 28)) == "D26102801"
        carga = _carga(db, "2026-10-28T09:00:00", 5_000, "D26102801")
        _carga(db, "2026-10-28T09:00:00", 1_000, "D26102801", origen=carga)  # hermana: mismo lote
        assert siguiente_lote_despacho(date(2026, 10, 28)) == "D26102802"
        assert siguiente_lote_despacho(date(2026, 10, 29)) == "D26102901"


def test_carga_asigna_lote_de_despacho(app):
    from datetime import datetime

    from app.extensions import db
    from app.models import Entrega
    from app.services import entregas_service

    with app.app_context():
        e = Entrega(
            cliente="Cliente", lugar_entrega="Planta", producto="Otro producto", cantidad=100, unidad="L",
            fecha_prevista="2026-10-28", estado="programada", created_at_iso="2026-10-28T08:00:00",
            updated_at_iso="2026-10-28T08:00:00",
        )
        db.session.add(e)
        db.session.flush()
        entregas_service.ejecutar_cargada(e, None, datetime(2026, 10, 28, 10, 0))
        assert e.lote_despacho == "D26102801"


def test_origen_cubre_tres_veces_el_stock_del_pulmon(app):
    from app.extensions import db
    from app.models import User
    from app.services import trazabilidad_service as ts

    with app.app_context():
        cierres = _escenario(db, User)
        # Al cargar hay 5.000 L (último cierre): hacen falta 15.000 L de producción, más de lo registrado.
        v = ts._Pulmon().ventana("2026-05-02T15:00:00")
        assert v["stock"] == 5_000.0
        assert not v["completa"]
        # Con factor 1 alcanzan los turnos que repusieron esos 5.000 L... pero solo hay 4.000 producidos.
        ts_factor = ts.FACTOR_PULMON
        try:
            ts.FACTOR_PULMON = 0.5  # 2.500 L → tres turnos
            v = ts._Pulmon().ventana("2026-05-02T15:00:00")
            assert v["completa"]
            assert v["desde"] == cierres[1]
            assert len(v["turnos"]) == 3
        finally:
            ts.FACTOR_PULMON = ts_factor


def test_lote_despacho_hacia_atras_y_lote_mp_hacia_adelante(app, monkeypatch):
    from app.extensions import db
    from app.models import User
    from app.services import trazabilidad_service as ts

    monkeypatch.setattr(ts, "FACTOR_PULMON", 0.5)
    with app.app_context():
        _escenario(db, User)
        sal_vieja = _mp(db, "Sal Gruesa Lavada", "S-1", "2026-04-25", [("2026-04-30", "10:00")])
        sal_nueva = _mp(db, "Sal Gruesa Lavada", "S-2", "2026-04-30", [("2026-05-01", "16:00"), ("2026-05-02", "08:00")])
        carga = _carga(db, "2026-05-02T15:00:00", 3_000, "D26050201", cliente="Municipio")
        _carga(db, "2026-05-02T15:00:00", 500, "D26050201", cliente="Cooperativa", origen=carga)
        db.session.commit()

        d = ts.detalle_lote_despacho("d26050201")
        assert {e.cliente for e in d["entregas"]} == {"Municipio", "Cooperativa"}
        lotes = {(m["lote"], m["previo"]) for m in d["materias_primas"]}
        assert ("S-2", False) in lotes
        assert ("S-1", True) in lotes  # estaba en uso cuando empezó el período

        r = ts.rastrear_ingreso(int(sal_nueva.id))
        assert [c["carga"].lote_despacho for c in r["cargas"]] == ["D26050201"]
        # El lote viejo dejó de usarse el 01/05 a las 16:00, dentro del origen de la carga.
        r = ts.rastrear_ingreso(int(sal_vieja.id))
        assert r["uso"]["hasta"] == "2026-05-01T16:00"
        assert [c["carga"].lote_despacho for c in r["cargas"]] == ["D26050201"]

        assert ts.buscar("s-2")["ingresos"][0].id == sal_nueva.id
        assert ts.buscar("D26050201")["tipo"] == "despacho"


def test_pantalla_trazabilidad(auth_client, app):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        _escenario(db, User)
        _carga(db, "2026-05-02T15:00:00", 3_000, "D26050201", cliente="Municipio")
        db.session.commit()
    r = auth_client.get("/trazabilidad/?q=D26050201")
    assert r.status_code == 200
    assert "Municipio" in r.get_data(as_text=True)
    r = auth_client.get("/trazabilidad/?q=no-existe")
    assert "No hay ningún lote" in r.get_data(as_text=True)
