from __future__ import annotations


def test_personal_hub_ok(auth_client):
    r = auth_client.get("/personal/", follow_redirects=True)
    assert r.status_code == 200
    assert b"Personal" in r.data


def test_personal_blocked_nonprivileged(mant_client):
    r = mant_client.get("/personal/", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_personal_legajo_crud(auth_client):
    r = auth_client.get("/personal/legajos/nuevo")
    assert r.status_code == 200

    r = auth_client.post(
        "/personal/legajos/nuevo",
        data={
            "legajo": "L-001",
            "apellido": "García",
            "nombre": "Juan",
            "puesto": "Operador",
            "estado": "activo",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    r = auth_client.get("/personal/legajos?q=Garc")
    assert r.status_code == 200
    assert b"Garc" in r.data

    r = auth_client.post(
        "/personal/epp/catalogo",
        data={"nombre": "Guantes nitrilo", "categoria": "epp", "requiere_talle": "1", "activo": "1"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    r = auth_client.get("/personal/epp/catalogo")
    assert b"Guantes nitrilo" in r.data

    r = auth_client.get("/personal/vacaciones")
    assert r.status_code == 200
