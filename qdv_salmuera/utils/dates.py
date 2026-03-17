from __future__ import annotations

from datetime import date, datetime


def parse_date_ddmmyyyy(s: str) -> date | None:
    """Recibe DD/MM/YYYY y devuelve un objeto date. Si falla, devuelve None."""
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").date()
    except Exception:
        return None


def date_to_iso(d: date) -> str:
    """Recibe un objeto date y devuelve YYYY-MM-DD."""
    return d.isoformat()


def iso_to_ddmmyyyy(s: str) -> str:
    """Recibe YYYY-MM-DD y devuelve DD/MM/YYYY."""
    try:
        dt = datetime.strptime(s.strip(), "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return s