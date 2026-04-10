"""Formato de fecha/hora operativa para panel y listados de consumo."""

from __future__ import annotations

import os

import pytest

from app.utils.datetime_operacion import (
    format_consumo_stock_panel_datetime,
    format_iso_timestamp_for_panel,
)


def test_format_consumo_fallback_fecha_hora_columns():
    assert (
        format_consumo_stock_panel_datetime(None, "2025-06-10", "08:05")
        == "2025-06-10 08:05"
    )
    assert format_consumo_stock_panel_datetime("not-iso", "2025-06-10", "08:05") == "2025-06-10 08:05"


def test_format_consumo_prefers_created_at_iso_when_parseable():
    assert (
        format_consumo_stock_panel_datetime("2025-06-10T08:05:00", "1999-01-01", "00:00")
        == "2025-06-10 08:05"
    )


def test_format_iso_z_converted_to_operacion_tz(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_TIMEZONE", "America/Argentina/Buenos_Aires")
    # 18:00 UTC = 15:00 ART (UTC-3) en junio
    out = format_iso_timestamp_for_panel("2025-06-10T18:00:00Z")
    assert out == "2025-06-10 15:00"


def test_panel_naive_iso_as_utc_when_env_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_TIMEZONE", "America/Argentina/Buenos_Aires")
    monkeypatch.setenv("APP_PANEL_NAIVE_ISO_IS_UTC", "1")
    out = format_iso_timestamp_for_panel("2025-06-10T18:00:00")
    assert out == "2025-06-10 15:00"
