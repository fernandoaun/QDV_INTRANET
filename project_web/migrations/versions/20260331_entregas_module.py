"""tablas entregas y entrega_eventos

Revision ID: 20260331_entregas_module
Revises: 20260331_user_fullname_stock_scopes
Create Date: 2026-03-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260331_entregas_module"
down_revision: Union[str, Sequence[str], None] = "20260331_user_fullname_stock_scopes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entregas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cliente", sa.String(length=256), nullable=False),
        sa.Column("lugar_entrega", sa.String(length=512), nullable=False),
        sa.Column("producto", sa.String(length=256), nullable=False),
        sa.Column("cantidad", sa.Float(), nullable=False),
        sa.Column("unidad", sa.String(length=64), nullable=True),
        sa.Column("fecha_prevista", sa.String(length=16), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("chofer_previsto", sa.String(length=256), nullable=True),
        sa.Column("estado", sa.String(length=32), nullable=False),
        sa.Column("created_at_iso", sa.String(length=32), nullable=False),
        sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("cargada_at_iso", sa.String(length=32), nullable=True),
        sa.Column("cargada_by_user_id", sa.Integer(), nullable=True),
        sa.Column("consumo_stock_id", sa.Integer(), nullable=True),
        sa.Column("stock_categoria", sa.String(length=32), nullable=True),
        sa.Column("stock_marca", sa.String(length=256), nullable=True),
        sa.Column("stock_equipo_id", sa.Integer(), nullable=True),
        sa.Column("entregada_at_iso", sa.String(length=32), nullable=True),
        sa.Column("entregada_by_user_id", sa.Integer(), nullable=True),
        sa.Column("entregada_chofer_nombre", sa.String(length=256), nullable=True),
        sa.Column("entregada_lugar", sa.String(length=512), nullable=True),
        sa.Column("entregada_dia_semana", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["cargada_by_user_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["consumo_stock_id"], ["consumos_stock.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["entregada_by_user_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["stock_equipo_id"], ["equipos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("consumo_stock_id"),
    )
    op.create_index(op.f("ix_entregas_estado"), "entregas", ["estado"], unique=False)
    op.create_index(op.f("ix_entregas_fecha_prevista"), "entregas", ["fecha_prevista"], unique=False)

    op.create_table(
        "entrega_eventos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entrega_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("at_iso", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_display", sa.String(length=256), nullable=False),
        sa.Column("detalle", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["entrega_id"], ["entregas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_entrega_eventos_entrega_id"), "entrega_eventos", ["entrega_id"], unique=False)
    op.create_index(op.f("ix_entrega_eventos_tipo"), "entrega_eventos", ["tipo"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_entrega_eventos_tipo"), table_name="entrega_eventos")
    op.drop_index(op.f("ix_entrega_eventos_entrega_id"), table_name="entrega_eventos")
    op.drop_table("entrega_eventos")
    op.drop_index(op.f("ix_entregas_fecha_prevista"), table_name="entregas")
    op.drop_index(op.f("ix_entregas_estado"), table_name="entregas")
    op.drop_table("entregas")
