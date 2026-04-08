"""Catálogos entregas (PT, cliente, lugar, chofer) y stock producto terminado

Revision ID: 20260408_entregas_catalogos
Revises: 20260407_producto_is_stockable
Create Date: 2026-04-08
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "20260408_entregas_catalogos"
down_revision: Union[str, Sequence[str], None] = "20260407_producto_is_stockable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HIPO_STOCK = "Hipoclorito"
_PT_CAT = "producto_terminado"
_PT_NOMBRE = "Hipoclorito de Sodio"


def upgrade() -> None:
    now = datetime.now().isoformat(timespec="seconds")
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())

    if "productos_terminados_entrega" not in existing:
        op.create_table(
            "productos_terminados_entrega",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("nombre", sa.String(length=256), nullable=False),
            sa.Column("stock_producto", sa.String(length=256), nullable=False),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at_iso", sa.String(length=32), nullable=False),
            sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "clientes_entrega" not in existing:
        op.create_table(
            "clientes_entrega",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("nombre", sa.String(length=256), nullable=False),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("observaciones", sa.Text(), nullable=True),
            sa.Column("created_at_iso", sa.String(length=32), nullable=False),
            sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "lugares_entrega" not in existing:
        op.create_table(
            "lugares_entrega",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("nombre", sa.String(length=512), nullable=False),
            sa.Column("cliente_id", sa.Integer(), nullable=False),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at_iso", sa.String(length=32), nullable=False),
            sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
            sa.ForeignKeyConstraint(["cliente_id"], ["clientes_entrega.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_lugares_entrega_cliente_id"), "lugares_entrega", ["cliente_id"], unique=False)

    if "choferes_entrega" not in existing:
        op.create_table(
            "choferes_entrega",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("nombre", sa.String(length=256), nullable=False),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("observaciones", sa.Text(), nullable=True),
            sa.Column("created_at_iso", sa.String(length=32), nullable=False),
            sa.Column("updated_at_iso", sa.String(length=32), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    insp = sa.inspect(bind)
    cols_ent = {c["name"] for c in insp.get_columns("entregas")}
    fks = {fk.get("name") for fk in insp.get_foreign_keys("entregas")}
    ix_ent = {i["name"] for i in insp.get_indexes("entregas")}

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("entregas") as batch_op:
            if "cliente_id" not in cols_ent:
                batch_op.add_column(sa.Column("cliente_id", sa.Integer(), nullable=True))
            if "lugar_entrega_id" not in cols_ent:
                batch_op.add_column(sa.Column("lugar_entrega_id", sa.Integer(), nullable=True))
            if "producto_terminado_id" not in cols_ent:
                batch_op.add_column(sa.Column("producto_terminado_id", sa.Integer(), nullable=True))
            if "chofer_entrega_id" not in cols_ent:
                batch_op.add_column(sa.Column("chofer_entrega_id", sa.Integer(), nullable=True))
            if "fk_entregas_cliente_entrega" not in fks:
                batch_op.create_foreign_key(
                    "fk_entregas_cliente_entrega", "clientes_entrega", ["cliente_id"], ["id"]
                )
            if "fk_entregas_lugar_entrega" not in fks:
                batch_op.create_foreign_key(
                    "fk_entregas_lugar_entrega", "lugares_entrega", ["lugar_entrega_id"], ["id"]
                )
            if "fk_entregas_producto_terminado" not in fks:
                batch_op.create_foreign_key(
                    "fk_entregas_producto_terminado",
                    "productos_terminados_entrega",
                    ["producto_terminado_id"],
                    ["id"],
                )
            if "fk_entregas_chofer_entrega" not in fks:
                batch_op.create_foreign_key(
                    "fk_entregas_chofer_entrega", "choferes_entrega", ["chofer_entrega_id"], ["id"]
                )
            inm = op.f("ix_entregas_cliente_id")
            if inm not in ix_ent:
                batch_op.create_index(inm, ["cliente_id"], unique=False)
            inm = op.f("ix_entregas_lugar_entrega_id")
            if inm not in ix_ent:
                batch_op.create_index(inm, ["lugar_entrega_id"], unique=False)
            inm = op.f("ix_entregas_producto_terminado_id")
            if inm not in ix_ent:
                batch_op.create_index(inm, ["producto_terminado_id"], unique=False)
            inm = op.f("ix_entregas_chofer_entrega_id")
            if inm not in ix_ent:
                batch_op.create_index(inm, ["chofer_entrega_id"], unique=False)
    else:
        if "cliente_id" not in cols_ent:
            op.add_column("entregas", sa.Column("cliente_id", sa.Integer(), nullable=True))
        if "lugar_entrega_id" not in cols_ent:
            op.add_column("entregas", sa.Column("lugar_entrega_id", sa.Integer(), nullable=True))
        if "producto_terminado_id" not in cols_ent:
            op.add_column("entregas", sa.Column("producto_terminado_id", sa.Integer(), nullable=True))
        if "chofer_entrega_id" not in cols_ent:
            op.add_column("entregas", sa.Column("chofer_entrega_id", sa.Integer(), nullable=True))
        if "fk_entregas_cliente_entrega" not in fks:
            op.create_foreign_key("fk_entregas_cliente_entrega", "entregas", "clientes_entrega", ["cliente_id"], ["id"])
        if "fk_entregas_lugar_entrega" not in fks:
            op.create_foreign_key("fk_entregas_lugar_entrega", "entregas", "lugares_entrega", ["lugar_entrega_id"], ["id"])
        if "fk_entregas_producto_terminado" not in fks:
            op.create_foreign_key(
                "fk_entregas_producto_terminado",
                "entregas",
                "productos_terminados_entrega",
                ["producto_terminado_id"],
                ["id"],
            )
        if "fk_entregas_chofer_entrega" not in fks:
            op.create_foreign_key("fk_entregas_chofer_entrega", "entregas", "choferes_entrega", ["chofer_entrega_id"], ["id"])
        if op.f("ix_entregas_cliente_id") not in ix_ent:
            op.create_index(op.f("ix_entregas_cliente_id"), "entregas", ["cliente_id"], unique=False)
        if op.f("ix_entregas_lugar_entrega_id") not in ix_ent:
            op.create_index(op.f("ix_entregas_lugar_entrega_id"), "entregas", ["lugar_entrega_id"], unique=False)
        if op.f("ix_entregas_producto_terminado_id") not in ix_ent:
            op.create_index(op.f("ix_entregas_producto_terminado_id"), "entregas", ["producto_terminado_id"], unique=False)
        if op.f("ix_entregas_chofer_entrega_id") not in ix_ent:
            op.create_index(op.f("ix_entregas_chofer_entrega_id"), "entregas", ["chofer_entrega_id"], unique=False)

    seed_pt = bind.execute(
        text("SELECT 1 FROM productos_terminados_entrega WHERE lower(trim(nombre)) = lower(trim(:n)) LIMIT 1"),
        {"n": _PT_NOMBRE},
    ).fetchone()
    if not seed_pt:
        bind.execute(
            text(
                "INSERT INTO productos_terminados_entrega (nombre, stock_producto, activo, created_at_iso, updated_at_iso) "
                "VALUES (:n, :sp, 1, :ts, :ts)"
            ),
            {"n": _PT_NOMBRE, "sp": _HIPO_STOCK, "ts": now},
        )

    n_mp = bind.execute(
        text(
            "SELECT COUNT(*) FROM productos_catalogo WHERE categoria = 'materia_prima' "
            "AND lower(trim(nombre_producto)) = lower(trim(:h))"
        ),
        {"h": _HIPO_STOCK},
    ).scalar()
    if int(n_mp or 0) > 0:
        bind.execute(
            text(
                "UPDATE productos_catalogo SET categoria = :pt WHERE categoria = 'materia_prima' "
                "AND lower(trim(nombre_producto)) = lower(trim(:h))"
            ),
            {"pt": _PT_CAT, "h": _HIPO_STOCK},
        )
        bind.execute(
            text(
                "DELETE FROM productos_catalogo WHERE categoria = 'laboratorio' "
                "AND lower(trim(nombre_producto)) = lower(trim(:h))"
            ),
            {"h": _HIPO_STOCK},
        )
    else:
        bind.execute(
            text(
                "UPDATE productos_catalogo SET categoria = :pt WHERE categoria = 'laboratorio' "
                "AND lower(trim(nombre_producto)) = lower(trim(:h))"
            ),
            {"pt": _PT_CAT, "h": _HIPO_STOCK},
        )

    bind.execute(
        text(
            "UPDATE ingresos_stock SET categoria = :pt WHERE categoria IN ('materia_prima','laboratorio') "
            "AND lower(trim(producto)) = lower(trim(:h))"
        ),
        {"pt": _PT_CAT, "h": _HIPO_STOCK},
    )
    bind.execute(
        text(
            "UPDATE consumos_stock SET categoria = :pt WHERE categoria IN ('materia_prima','laboratorio') "
            "AND lower(trim(producto)) = lower(trim(:h))"
        ),
        {"pt": _PT_CAT, "h": _HIPO_STOCK},
    )

    bind.execute(
        text(
            "UPDATE entregas SET stock_categoria = :pt WHERE stock_categoria IN ('materia_prima','laboratorio') "
            "AND lower(trim(producto)) = lower(trim(:h))"
        ),
        {"pt": _PT_CAT, "h": _HIPO_STOCK},
    )
    bind.execute(
        text(
            "UPDATE entregas SET stock_categoria = :pt WHERE (stock_categoria IS NULL OR trim(stock_categoria) = '') "
            "AND lower(trim(producto)) = lower(trim(:h))"
        ),
        {"pt": _PT_CAT, "h": _HIPO_STOCK},
    )

    has_pt_cat = bind.execute(
        text(
            "SELECT 1 FROM productos_catalogo WHERE categoria = :pt AND lower(trim(nombre_producto)) = lower(trim(:h)) LIMIT 1"
        ),
        {"pt": _PT_CAT, "h": _HIPO_STOCK},
    ).fetchone()
    if not has_pt_cat:
        bind.execute(
            text(
                "INSERT INTO productos_catalogo (categoria, nombre_producto, tipo_producto, requiere_equipo, "
                "is_stockable, stock_minimo_alerta, activo, created_at_iso) "
                "VALUES (:pt, :h, 'Normal', 0, 1, NULL, 1, :ts)"
            ),
            {"pt": _PT_CAT, "h": _HIPO_STOCK, "ts": now},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "UPDATE entregas SET stock_categoria = 'materia_prima' WHERE stock_categoria = :pt "
            "AND lower(trim(producto)) = lower(trim(:h))"
        ),
        {"pt": _PT_CAT, "h": _HIPO_STOCK},
    )
    bind.execute(
        text(
            "UPDATE consumos_stock SET categoria = 'materia_prima' WHERE categoria = :pt "
            "AND lower(trim(producto)) = lower(trim(:h))"
        ),
        {"pt": _PT_CAT, "h": _HIPO_STOCK},
    )
    bind.execute(
        text(
            "UPDATE ingresos_stock SET categoria = 'materia_prima' WHERE categoria = :pt "
            "AND lower(trim(producto)) = lower(trim(:h))"
        ),
        {"pt": _PT_CAT, "h": _HIPO_STOCK},
    )
    bind.execute(
        text(
            "UPDATE productos_catalogo SET categoria = 'materia_prima' WHERE categoria = :pt "
            "AND lower(trim(nombre_producto)) = lower(trim(:h))"
        ),
        {"pt": _PT_CAT, "h": _HIPO_STOCK},
    )

    op.drop_index(op.f("ix_entregas_chofer_entrega_id"), table_name="entregas")
    op.drop_index(op.f("ix_entregas_producto_terminado_id"), table_name="entregas")
    op.drop_index(op.f("ix_entregas_lugar_entrega_id"), table_name="entregas")
    op.drop_index(op.f("ix_entregas_cliente_id"), table_name="entregas")
    op.drop_constraint("fk_entregas_chofer_entrega", "entregas", type_="foreignkey")
    op.drop_constraint("fk_entregas_producto_terminado", "entregas", type_="foreignkey")
    op.drop_constraint("fk_entregas_lugar_entrega", "entregas", type_="foreignkey")
    op.drop_constraint("fk_entregas_cliente_entrega", "entregas", type_="foreignkey")
    op.drop_column("entregas", "chofer_entrega_id")
    op.drop_column("entregas", "producto_terminado_id")
    op.drop_column("entregas", "lugar_entrega_id")
    op.drop_column("entregas", "cliente_id")

    op.drop_table("choferes_entrega")
    op.drop_index(op.f("ix_lugares_entrega_cliente_id"), table_name="lugares_entrega")
    op.drop_table("lugares_entrega")
    op.drop_table("clientes_entrega")
    op.drop_table("productos_terminados_entrega")
