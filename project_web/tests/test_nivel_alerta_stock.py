"""Criterio de inclusión y severidad para alertas de stock en panel (redondeo 2 decimales)."""

from app.services.stock_service import _nivel_alerta_panel


def test_no_aparece_cuando_stock_mayor_al_minimo():
    assert _nivel_alerta_panel(120, 100) is None
    assert _nivel_alerta_panel(100.01, 100) is None


def test_limite_cuando_stock_igual_al_minimo():
    assert _nivel_alerta_panel(100, 100) == "limite"


def test_critico_cuando_stock_menor_al_minimo():
    assert _nivel_alerta_panel(80, 100) == "critico"


def test_redondeo_coherente_con_ui_dos_decimales():
    # 99.996 → 100.00 vs mínimo 100 → en el límite
    assert _nivel_alerta_panel(99.996, 100) == "limite"
    # 100.004 → 100.00 vs mínimo 100 → en el límite
    assert _nivel_alerta_panel(100.004, 100) == "limite"
    # 100.015 → 100.02 > 100 → fuera de alertas
    assert _nivel_alerta_panel(100.015, 100) is None
