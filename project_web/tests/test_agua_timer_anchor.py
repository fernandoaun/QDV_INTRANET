from __future__ import annotations

from app.extensions import db
from app.models import AguaRegistro, FiltroLavadoRegistro, ReactorRegistro, SalmueraRegistro
from app.services.filtro_lavado_service import last_filtro_created_at_iso
from app.web.modules.produccion.agua_helpers import (
    last_agua_created_at_iso,
    last_agua_created_at_iso_for_date,
)
from app.web.modules.produccion.reactor_helpers import last_reactor_created_at_iso
from app.web.modules.produccion.salmuera_helpers import last_salmuera_created_at_iso_for_electrolizador


def test_last_agua_created_at_iso_crosses_days(app):
    with app.app_context():
        db.session.add(
            AguaRegistro(
                fecha_iso="2026-08-05",
                hora_hm="22:00",
                turno="N",
                operador="Op",
                lote="26080501",
                numero_columna=1,
                temperatura=25.0,
                dureza=0.5,
                observaciones="",
                created_at_iso="2026-08-05T22:00:00",
            )
        )
        db.session.commit()

        assert last_agua_created_at_iso_for_date("2026-08-06") is None
        assert last_agua_created_at_iso() == "2026-08-05T22:00:00"


def test_last_reactor_uses_latest_created_at_not_max_id(app):
    with app.app_context():
        common = dict(
            fecha_iso="2026-09-03",
            operador="Op",
            ph=7.0,
            temperatura=25.0,
            densidad=1.2,
            concentracion_tabla=300.0,
            exceso_naoh=0.1,
            exceso_na2co3=0.1,
        )
        db.session.add(
            ReactorRegistro(
                **common,
                hora_hm="13:46",
                lote="26090301",
                created_at_iso="2026-09-03T13:46:20",
            )
        )
        db.session.add(
            ReactorRegistro(
                **common,
                hora_hm="13:08",
                lote="26090302",
                created_at_iso="2026-09-03T13:08:00",
            )
        )
        db.session.commit()
        assert last_reactor_created_at_iso() == "2026-09-03T13:46:20"


def test_last_reactor_anchor_prefers_fecha_hora_over_stale_created_at(app):
    """Si created_at quedó viejo pero fecha/hora del registro son de hoy, el cronómetro usa eso."""
    with app.app_context():
        common = dict(
            operador="Op",
            ph=7.0,
            temperatura=25.0,
            densidad=1.2,
            concentracion_tabla=300.0,
            exceso_naoh=0.1,
            exceso_na2co3=0.1,
        )
        db.session.add(
            ReactorRegistro(
                **common,
                fecha_iso="2026-09-04",
                hora_hm="18:38",
                lote="26090401",
                created_at_iso="2026-09-04T18:38:40",
            )
        )
        db.session.add(
            ReactorRegistro(
                **common,
                fecha_iso="2026-09-05",
                hora_hm="15:02",
                lote="26090507",
                created_at_iso="2026-09-04T12:00:00",
            )
        )
        db.session.commit()
        assert last_reactor_created_at_iso() == "2026-09-05T15:02:00"


def test_last_filtro_anchor_prefers_fecha_hora_over_stale_created_at(app):
    with app.app_context():
        db.session.add(
            FiltroLavadoRegistro(
                fecha_iso="2026-09-04",
                hora_hm="10:00",
                operador="Op",
                observaciones="",
                created_at_iso="2026-09-04T10:00:00",
            )
        )
        db.session.add(
            FiltroLavadoRegistro(
                fecha_iso="2026-09-05",
                hora_hm="08:30",
                operador="Op",
                observaciones="",
                created_at_iso="2026-09-04T09:00:00",  # stale
            )
        )
        db.session.commit()
        assert last_filtro_created_at_iso() == "2026-09-05T08:30:00"


def test_last_agua_anchor_prefers_fecha_hora_over_stale_created_at(app):
    with app.app_context():
        db.session.add(
            AguaRegistro(
                fecha_iso="2026-09-05",
                hora_hm="14:00",
                turno="T",
                operador="Op",
                lote="26090501",
                numero_columna=1,
                temperatura=25.0,
                dureza=0.5,
                observaciones="",
                created_at_iso="2026-09-04T11:00:00",
            )
        )
        db.session.commit()
        assert last_agua_created_at_iso() == "2026-09-05T14:00:00"


def test_last_salmuera_anchor_prefers_fecha_hora_over_stale_created_at(app):
    with app.app_context():
        common = dict(
            electrolizador=3,
            cantidad_celdas=6,
            turno="T",
            voltajes_json="[3.0,3.0,3.0,3.0,3.0,3.0]",
            voltaje_total=18.0,
            voltaje_total_trafo=110.0,
            amperaje=50.0,
            caudal_agua_l_h=10.0,
            caudal_salmuera_l_h=12.0,
            hipo_conc=1.0,
            hipo_exceso_soda=0.1,
            sal_temp=25.0,
            sal_conc=250.0,
            sal_ph=5.5,
            soda_conc=1.0,
            declor_ph=2.0,
            operador="Op",
            observaciones="",
        )
        db.session.add(
            SalmueraRegistro(
                **common,
                fecha_iso="2026-09-04",
                hora_hm="12:00",
                lote="26090401",
                created_at_iso="2026-09-04T12:00:00",
            )
        )
        db.session.add(
            SalmueraRegistro(
                **common,
                fecha_iso="2026-09-05",
                hora_hm="13:10",
                lote="26090502",
                created_at_iso="2026-09-04T08:00:00",
            )
        )
        db.session.commit()
        assert last_salmuera_created_at_iso_for_electrolizador(3) == "2026-09-05T13:10:00"
        assert last_salmuera_created_at_iso_for_electrolizador(2) is None
