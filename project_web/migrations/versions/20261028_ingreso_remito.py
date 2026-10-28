"""Ingresos de stock: remito y vencimiento siempre como fecha.

Sin lote del proveedor el ingreso se identifica por su remito; sin vencimiento, vence a un año del
ingreso. Los ingresos viejos con lote de relleno («1111», «00000», «S/L») no tienen remito cargado:
quedan identificados por su número de ingreso. Los vencimientos se pasan a dd/mm/aaaa.

Revision ID: 20261028_ingreso_remito
Revises: 20261028_lote_produccion_turno
Create Date: 2026-10-28
"""
from datetime import date

from alembic import op
import sqlalchemy as sa

revision: str = "20261028_ingreso_remito"
down_revision: str | None = "20261028_lote_produccion_turno"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    from app.services.stock_service import es_dato_de_relleno, vencimiento_de_ingreso

    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("ingresos_stock")}
    if "remito" not in cols:
        op.add_column("ingresos_stock", sa.Column("remito", sa.String(length=64), nullable=True))
        op.create_index("ix_ingresos_stock_remito", "ingresos_stock", ["remito"])

    for iid, lote, venc, fecha in bind.execute(sa.text("SELECT id, lote, vencimiento, fecha FROM ingresos_stock")).fetchall():
        nuevo_lote = f"Sin lote (ingreso {iid})" if es_dato_de_relleno(lote) else lote
        try:
            nuevo_venc = vencimiento_de_ingreso(venc, date.fromisoformat(fecha))
        except ValueError:
            nuevo_venc = vencimiento_de_ingreso("", date.fromisoformat(fecha))
        if (nuevo_lote, nuevo_venc) != (lote, venc):
            bind.execute(
                sa.text("UPDATE ingresos_stock SET lote = :l, vencimiento = :v WHERE id = :i"),
                {"l": nuevo_lote, "v": nuevo_venc, "i": iid},
            )


def downgrade():
    op.drop_index("ix_ingresos_stock_remito", table_name="ingresos_stock")
    op.drop_column("ingresos_stock", "remito")
