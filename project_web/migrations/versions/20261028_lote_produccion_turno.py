"""Lote de producción por turno (P + aammdd + correlativo) y lote observado.

Numera los turnos existentes por orden de inicio y pasa los análisis de agua, reactor y
salmuera al lote del turno en curso a su hora (el último iniciado hasta ese momento). El
número por análisis que tenían antes queda en ``analisis_lotes_anteriores``.

Revision ID: 20261028_lote_produccion_turno
Revises: 20261028_lote_despacho
Create Date: 2026-10-28
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261028_lote_produccion_turno"
down_revision: str | None = "20261028_lote_despacho"
branch_labels: str | None = None
depends_on: str | None = None

TABLAS = ("agua_registros", "reactor_registros", "salmuera_registros")


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("shift_sessions")}
    if "lote_produccion" not in cols:
        op.add_column("shift_sessions", sa.Column("lote_produccion", sa.String(length=32), nullable=True))
        op.create_index("ix_shift_sessions_lote_produccion", "shift_sessions", ["lote_produccion"])
        op.add_column("shift_sessions", sa.Column("lote_observado_nota", sa.Text(), nullable=True))
        op.add_column("shift_sessions", sa.Column("lote_observado_at_iso", sa.String(length=32), nullable=True))
        op.add_column(
            "shift_sessions",
            sa.Column("lote_observado_por_user_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        )
    if "analisis_lotes_anteriores" not in insp.get_table_names():
        op.create_table(
            "analisis_lotes_anteriores",
            sa.Column("tabla", sa.String(length=64), nullable=False),
            sa.Column("registro_id", sa.Integer(), nullable=False),
            sa.Column("lote", sa.String(length=128), nullable=True),
            sa.PrimaryKeyConstraint("tabla", "registro_id"),
        )

    sesiones = bind.execute(
        sa.text("SELECT id, started_at_iso FROM shift_sessions WHERE lote_produccion IS NULL ORDER BY started_at_iso, id")
    ).fetchall()
    por_dia: dict[str, int] = {}
    for sid, inicio in sesiones:
        dia = inicio[2:4] + inicio[5:7] + inicio[8:10]
        por_dia[dia] = por_dia.get(dia, 0) + 1
        bind.execute(
            sa.text("UPDATE shift_sessions SET lote_produccion = :l WHERE id = :i"),
            {"l": f"P{dia}{por_dia[dia]:02d}", "i": sid},
        )

    for tabla in TABLAS:
        bind.execute(
            sa.text(
                f"INSERT INTO analisis_lotes_anteriores (tabla, registro_id, lote) "
                f"SELECT '{tabla}', id, lote FROM {tabla} r "
                f"WHERE NOT EXISTS (SELECT 1 FROM analisis_lotes_anteriores a WHERE a.tabla = '{tabla}' AND a.registro_id = r.id)"
            )
        )
        turno = (
            "SELECT s.lote_produccion FROM shift_sessions s "
            f"WHERE s.lote_produccion IS NOT NULL AND s.started_at_iso <= {tabla}.fecha_iso || 'T' || {tabla}.hora_hm || :seg "
            "ORDER BY s.started_at_iso DESC, s.id DESC LIMIT 1"
        )
        bind.execute(sa.text(f"UPDATE {tabla} SET lote = ({turno}) WHERE EXISTS ({turno})"), {"seg": ":59"})


def downgrade():
    bind = op.get_bind()
    for tabla in TABLAS:
        bind.execute(
            sa.text(
                f"UPDATE {tabla} SET lote = (SELECT a.lote FROM analisis_lotes_anteriores a "
                f"WHERE a.tabla = '{tabla}' AND a.registro_id = {tabla}.id) "
                f"WHERE EXISTS (SELECT 1 FROM analisis_lotes_anteriores a WHERE a.tabla = '{tabla}' AND a.registro_id = {tabla}.id)"
            )
        )
    op.drop_table("analisis_lotes_anteriores")
    op.drop_column("shift_sessions", "lote_observado_por_user_id")
    op.drop_column("shift_sessions", "lote_observado_at_iso")
    op.drop_column("shift_sessions", "lote_observado_nota")
    op.drop_index("ix_shift_sessions_lote_produccion", table_name="shift_sessions")
    op.drop_column("shift_sessions", "lote_produccion")
