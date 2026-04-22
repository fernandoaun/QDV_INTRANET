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
