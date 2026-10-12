"""Confirmación de entregas EPP desde el link del aviso (sin login)."""
from __future__ import annotations

from datetime import date


def _entregas(app, *, anterior_sin_devolver: bool = False):
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEntregaEpp, PersonalEppItem

    with app.app_context():
        emp = EmpleadoPersonal(legajo="LNK-1", apellido="Link", nombre="Ana", fecha_ingreso=date(2026, 1, 1))
        otro = EmpleadoPersonal(legajo="LNK-2", apellido="Otro", nombre="Beto", fecha_ingreso=date(2026, 1, 1))
        item = PersonalEppItem(nombre="Botín link", categoria="epp", activo=True)
        db.session.add_all([emp, otro, item])
        db.session.flush()
        previa = PersonalEntregaEpp(empleado_id=emp.id, item_id=item.id, fecha=date(2026, 1, 5), estado="confirmada")
        db.session.add(previa)
        db.session.flush()
        en = PersonalEntregaEpp(
            empleado_id=emp.id,
            item_id=item.id,
            fecha=date(2026, 6, 10),
            talle="42",
            estado="pendiente",
            prenda_anterior_entrega_id=previa.id if anterior_sin_devolver else None,
        )
        ajena = PersonalEntregaEpp(empleado_id=otro.id, item_id=item.id, fecha=date(2026, 6, 10), estado="pendiente")
        db.session.add_all([en, ajena])
        db.session.commit()
        return emp.id, en.id, ajena.id


def _token(app, emp_id, ids):
    from app.extensions import db
    from app.models import EmpleadoPersonal, PersonalEntregaEpp
    from app.services.epp_confirmacion_link_service import crear_token

    with app.app_context():
        emp = db.session.get(EmpleadoPersonal, emp_id)
        return crear_token(app, emp, [db.session.get(PersonalEntregaEpp, i) for i in ids])


def _estado(app, entrega_id):
    from app.extensions import db
    from app.models import PersonalEntregaEpp

    with app.app_context():
        return db.session.get(PersonalEntregaEpp, entrega_id).estado


def test_link_confirma_sin_login(app, client):
    emp_id, en_id, _ = _entregas(app)
    url = f"/personal/epp/confirmar/{_token(app, emp_id, [en_id])}"

    r = client.get(url)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Botín link" in html and "10/06/2026" in html and "Sí, la recibí" in html
    assert _estado(app, en_id) == "pendiente"

    r = client.post(url)
    assert r.status_code == 200
    assert "Quedó registrado" in r.get_data(as_text=True)
    assert _estado(app, en_id) == "confirmada"

    # Volver a abrir el link no rompe nada.
    r = client.post(url)
    assert "No hay nada para confirmar" in r.get_data(as_text=True)


def test_link_no_confirma_entregas_de_otro_legajo(app, client):
    emp_id, _, ajena_id = _entregas(app)
    client.post(f"/personal/epp/confirmar/{_token(app, emp_id, [ajena_id])}")
    assert _estado(app, ajena_id) == "pendiente"


def test_link_respeta_devolucion_de_prenda_anterior(app, client):
    emp_id, en_id, _ = _entregas(app, anterior_sin_devolver=True)
    r = client.post(f"/personal/epp/confirmar/{_token(app, emp_id, [en_id])}")
    assert "prenda anterior" in r.get_data(as_text=True)
    assert _estado(app, en_id) == "pendiente"


def test_link_invalido(client):
    r = client.get("/personal/epp/confirmar/cualquiera")
    assert r.status_code == 200
    assert "no es válido" in r.get_data(as_text=True)
