"""SGC: registros digitales parametrizados (Word/Excel) vinculados al punto 7.

Revision ID: 20260721_sgi_record_definitions
Revises: 20260721_sgi_to_sgc_msgi_to_msgc
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_sgi_record_definitions"
down_revision: Union[str, Sequence[str], None] = "20260721_sgi_to_sgc_msgi_to_msgc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "sgi_record_files" not in tables:
        op.create_table(
            "sgi_record_files",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("original_name", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("safe_name", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("extension", sa.String(length=16), nullable=False, server_default=""),
            sa.Column("mime_type", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("content_hash", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("storage_path", sa.String(length=1024), nullable=False, server_default=""),
            sa.Column("analysis_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["uploaded_by_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_sgi_record_files_content_hash", "sgi_record_files", ["content_hash"])
        op.create_index("ix_sgi_record_files_uploaded_by_id", "sgi_record_files", ["uploaded_by_id"])
        op.create_index("ix_sgi_record_files_uploaded_at", "sgi_record_files", ["uploaded_at"])

    if "sgi_record_definitions" not in tables:
        op.create_table(
            "sgi_record_definitions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("name", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("description", sa.String(length=4000), nullable=False, server_default=""),
            sa.Column("origin_type", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("source_file_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="activo"),
            sa.Column("current_version_id", sa.Integer(), nullable=True),
            sa.Column("created_by_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_by_id", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["source_file_id"], ["sgi_record_files.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_sgi_record_definitions_code", "sgi_record_definitions", ["code"])
        op.create_index("ix_sgi_record_definitions_origin_type", "sgi_record_definitions", ["origin_type"])
        op.create_index("ix_sgi_record_definitions_status", "sgi_record_definitions", ["status"])
        op.create_index("ix_sgi_record_definitions_source_file_id", "sgi_record_definitions", ["source_file_id"])
        op.create_index("ix_sgi_record_definitions_created_by_id", "sgi_record_definitions", ["created_by_id"])
        op.create_index("ix_sgi_record_definitions_created_at", "sgi_record_definitions", ["created_at"])
        op.create_index("ix_sgi_record_definitions_updated_by_id", "sgi_record_definitions", ["updated_by_id"])
        op.create_index("ix_sgi_record_definitions_deleted_at", "sgi_record_definitions", ["deleted_at"])
        op.create_index("ix_sgi_record_definitions_current_version_id", "sgi_record_definitions", ["current_version_id"])

    if "sgi_record_definition_versions" not in tables:
        op.create_table(
            "sgi_record_definition_versions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("record_definition_id", sa.Integer(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("schema_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("ui_schema_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("change_description", sa.String(length=2000), nullable=False, server_default=""),
            sa.Column("created_by_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["record_definition_id"], ["sgi_record_definitions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("record_definition_id", "version_number", name="uq_sgi_record_def_version"),
        )
        op.create_index(
            "ix_sgi_record_definition_versions_record_definition_id",
            "sgi_record_definition_versions",
            ["record_definition_id"],
        )
        op.create_index(
            "ix_sgi_record_definition_versions_created_by_id",
            "sgi_record_definition_versions",
            ["created_by_id"],
        )
        op.create_index(
            "ix_sgi_record_definition_versions_created_at",
            "sgi_record_definition_versions",
            ["created_at"],
        )

    if "sgi_record_entries" not in tables:
        op.create_table(
            "sgi_record_entries",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("record_definition_id", sa.Integer(), nullable=False),
            sa.Column("record_definition_version_id", sa.Integer(), nullable=False),
            sa.Column("entry_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="borrador"),
            sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_by_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_by_id", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["record_definition_id"], ["sgi_record_definitions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["record_definition_version_id"],
                ["sgi_record_definition_versions.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_sgi_record_entries_record_definition_id", "sgi_record_entries", ["record_definition_id"])
        op.create_index(
            "ix_sgi_record_entries_record_definition_version_id",
            "sgi_record_entries",
            ["record_definition_version_id"],
        )
        op.create_index("ix_sgi_record_entries_status", "sgi_record_entries", ["status"])
        op.create_index("ix_sgi_record_entries_created_by_id", "sgi_record_entries", ["created_by_id"])
        op.create_index("ix_sgi_record_entries_created_at", "sgi_record_entries", ["created_at"])
        op.create_index("ix_sgi_record_entries_updated_by_id", "sgi_record_entries", ["updated_by_id"])

    if "sgi_record_audit_logs" not in tables:
        op.create_table(
            "sgi_record_audit_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("entity_id", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("action", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("previous_data", sa.Text(), nullable=True),
            sa.Column("new_data", sa.Text(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_sgi_record_audit_logs_entity_type", "sgi_record_audit_logs", ["entity_type"])
        op.create_index("ix_sgi_record_audit_logs_entity_id", "sgi_record_audit_logs", ["entity_id"])
        op.create_index("ix_sgi_record_audit_logs_action", "sgi_record_audit_logs", ["action"])
        op.create_index("ix_sgi_record_audit_logs_user_id", "sgi_record_audit_logs", ["user_id"])
        op.create_index("ix_sgi_record_audit_logs_created_at", "sgi_record_audit_logs", ["created_at"])

    if "sgi_procedimiento_registros" in tables:
        cols = {c["name"] for c in insp.get_columns("sgi_procedimiento_registros")}
        if "association_type" not in cols:
            op.add_column(
                "sgi_procedimiento_registros",
                sa.Column("association_type", sa.String(length=32), nullable=False, server_default=""),
            )
        if "record_definition_id" not in cols:
            op.add_column(
                "sgi_procedimiento_registros",
                sa.Column("record_definition_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "fk_sgi_proc_reg_record_definition",
                "sgi_procedimiento_registros",
                "sgi_record_definitions",
                ["record_definition_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index(
                "ix_sgi_procedimiento_registros_record_definition_id",
                "sgi_procedimiento_registros",
                ["record_definition_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "sgi_procedimiento_registros" in tables:
        cols = {c["name"] for c in insp.get_columns("sgi_procedimiento_registros")}
        if "record_definition_id" in cols:
            try:
                op.drop_constraint("fk_sgi_proc_reg_record_definition", "sgi_procedimiento_registros", type_="foreignkey")
            except Exception:
                pass
            try:
                op.drop_index("ix_sgi_procedimiento_registros_record_definition_id", table_name="sgi_procedimiento_registros")
            except Exception:
                pass
            op.drop_column("sgi_procedimiento_registros", "record_definition_id")
        if "association_type" in cols:
            op.drop_column("sgi_procedimiento_registros", "association_type")

    for name in (
        "sgi_record_audit_logs",
        "sgi_record_entries",
        "sgi_record_definition_versions",
        "sgi_record_definitions",
        "sgi_record_files",
    ):
        if name in tables:
            op.drop_table(name)
