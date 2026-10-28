"""Lote de despacho por carga de camión (trazabilidad hacia el cliente).

Asigna lote a las cargas ya registradas: D + aammdd + correlativo del día, por orden
de carga; las entregas hermanas (reparto de una misma carga) toman el lote del origen.

Revision ID: 20261028_lote_despacho
Revises: 20261027_capacitacion
Create Date: 2026-10-28
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261028_lote_despacho"
down_revision: str | None = "20261027_capacitacion"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("entregas")}
    if "lote_despacho" not in cols:
        op.add_column("entregas", sa.Column("lote_despacho", sa.String(length=32), nullable=True))
        op.create_index("ix_entregas_lote_despacho", "entregas", ["lote_despacho"])

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, cargada_at_iso, carga_origen_entrega_id FROM entregas "
            "WHERE cargada_at_iso IS NOT NULL AND trim(cargada_at_iso) <> '' AND lote_despacho IS NULL "
            "ORDER BY cargada_at_iso, id"
        )
    ).fetchall()
    por_dia: dict[str, int] = {}
    asignado: dict[int, str] = {}
    hermanas = []
    for eid, cargada, origen_id in rows:
        if origen_id is not None:
            hermanas.append((eid, origen_id))
            continue
        dia = cargada[2:4] + cargada[5:7] + cargada[8:10]
        por_dia[dia] = por_dia.get(dia, 0) + 1
        asignado[eid] = f"D{dia}{por_dia[dia]:02d}"
    for eid, origen_id in hermanas:
        lote = asignado.get(origen_id) or bind.execute(
            sa.text("SELECT lote_despacho FROM entregas WHERE id = :i"), {"i": origen_id}
        ).scalar()
        if lote:
            asignado[eid] = lote
    for eid, lote in asignado.items():
        bind.execute(sa.text("UPDATE entregas SET lote_despacho = :l WHERE id = :i"), {"l": lote, "i": eid})


def downgrade():
    op.drop_index("ix_entregas_lote_despacho", table_name="entregas")
    op.drop_column("entregas", "lote_despacho")
