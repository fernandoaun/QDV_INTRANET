"""SGI: mover a papelera QDV-ANEXO III y IV recreados por seed.

Revision ID: 20260714_sgi_soft_delete_msgi_anexos_iii_iv
Revises: 20260714_sgi_registro_modulo
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_sgi_soft_delete_msgi_anexos_iii_iv"
down_revision: Union[str, Sequence[str], None] = "20260714_sgi_registro_modulo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CODIGOS = ("QDV-ANEXO III", "QDV-ANEXO IV")


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sgi_documentos" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sgi_documentos")}
    if "deleted_at" not in cols or "codigo_archivado" not in cols:
        return

    docs = sa.table(
        "sgi_documentos",
        sa.column("id", sa.Integer),
        sa.column("tipo", sa.String),
        sa.column("codigo", sa.String),
        sa.column("codigo_archivado", sa.String),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    rows = bind.execute(
        sa.select(docs.c.id, docs.c.codigo).where(
            docs.c.tipo == "MSGI",
            sa.func.upper(docs.c.codigo).in_(_CODIGOS),
            docs.c.deleted_at.is_(None),
        )
    ).fetchall()
    for row in rows:
        doc_id = int(row.id)
        codigo = (row.codigo or "").strip().upper()
        suffix = f"__ELIM_{doc_id}"
        base = codigo[: max(1, 64 - len(suffix))]
        bind.execute(
            docs.update()
            .where(docs.c.id == doc_id)
            .values(
                codigo_archivado=codigo[:64],
                codigo=f"{base}{suffix}"[:64],
                deleted_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    """No revierte: recuperar desde la UI «Documentos eliminados»."""
    pass
