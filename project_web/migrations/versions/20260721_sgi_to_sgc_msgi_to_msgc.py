"""Renombrar tipo MSGI → MSGC y códigos QDV-MSGI- → QDV-MSGC-.

Revision ID: 20260721_sgi_to_sgc_msgi_to_msgc
Revises: 20260714_sgi_soft_delete_msgi_anexos_iii_iv
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_sgi_to_sgc_msgi_to_msgc"
down_revision: Union[str, Sequence[str], None] = "20260714_sgi_soft_delete_msgi_anexos_iii_iv"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_documentos" not in insp.get_table_names():
        return
    docs = sa.table(
        "sgi_documentos",
        sa.column("id", sa.Integer),
        sa.column("tipo", sa.String),
        sa.column("codigo", sa.String),
        sa.column("codigo_archivado", sa.String),
    )
    bind.execute(docs.update().where(docs.c.tipo == "MSGI").values(tipo="MSGC"))
    rows = bind.execute(
        sa.select(docs.c.id, docs.c.codigo, docs.c.codigo_archivado).where(
            or_codigo_msgi(docs)
        )
    ).fetchall()
    for row in rows:
        new_codigo = _rename_msgi_codigo(row.codigo)
        new_arch = _rename_msgi_codigo(row.codigo_archivado)
        if new_codigo != row.codigo or new_arch != row.codigo_archivado:
            bind.execute(
                docs.update()
                .where(docs.c.id == row.id)
                .values(codigo=new_codigo, codigo_archivado=new_arch)
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_documentos" not in insp.get_table_names():
        return
    docs = sa.table(
        "sgi_documentos",
        sa.column("id", sa.Integer),
        sa.column("tipo", sa.String),
        sa.column("codigo", sa.String),
        sa.column("codigo_archivado", sa.String),
    )
    bind.execute(docs.update().where(docs.c.tipo == "MSGC").values(tipo="MSGI"))
    rows = bind.execute(
        sa.select(docs.c.id, docs.c.codigo, docs.c.codigo_archivado).where(
            or_codigo_msgc(docs)
        )
    ).fetchall()
    for row in rows:
        new_codigo = _rename_msgc_codigo(row.codigo)
        new_arch = _rename_msgc_codigo(row.codigo_archivado)
        if new_codigo != row.codigo or new_arch != row.codigo_archivado:
            bind.execute(
                docs.update()
                .where(docs.c.id == row.id)
                .values(codigo=new_codigo, codigo_archivado=new_arch)
            )


def or_codigo_msgi(docs):
    return sa.or_(
        docs.c.codigo.ilike("QDV-MSGI-%"),
        docs.c.codigo_archivado.ilike("QDV-MSGI-%"),
    )


def or_codigo_msgc(docs):
    return sa.or_(
        docs.c.codigo.ilike("QDV-MSGC-%"),
        docs.c.codigo_archivado.ilike("QDV-MSGC-%"),
    )


def _rename_msgi_codigo(value: str | None) -> str | None:
    if not value:
        return value
    upper = value.upper()
    if upper.startswith("QDV-MSGI-"):
        return "QDV-MSGC-" + value[len("QDV-MSGI-") :]
    return value


def _rename_msgc_codigo(value: str | None) -> str | None:
    if not value:
        return value
    upper = value.upper()
    if upper.startswith("QDV-MSGC-"):
        return "QDV-MSGI-" + value[len("QDV-MSGC-") :]
    return value
