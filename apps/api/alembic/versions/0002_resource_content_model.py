"""Milestone 4: evolve Document into Resource (nullable storage fields,
content_source discriminator, text_hash dedup)

Revision ID: 0002_resource_content_model
Revises: 0001_baseline_schema
Create Date: 2026-07-21

Implements the two DRR-approved Milestone 4 items:

1. Resource supports both file-backed and fileless resources: adds the
   `content_source` discriminator (backfilled to 'file' for every existing
   row, since every resource created before this migration came from the
   Milestone 3 upload path), and relaxes filename/storage_key/mime_type/
   size_bytes/checksum to nullable (still populated together for every FILE
   resource at the application layer -- see app/models/resource.py).
2. Adds `text_hash` for content-level dedup (nullable; backfilled by
   ingestion for existing FILE resources only the next time they are
   re-processed -- this migration does not attempt to compute it for
   historical rows, since that would mean re-reading every stored file
   from a migration, which is an operational decision, not a schema one).

Renames, table by table:
    documents        -> resources          (+ new/altered columns above)
    document_pages   -> resource_pages     (document_id -> resource_id)
    document_chunks  -> resource_chunks    (document_id -> resource_id)
    ingestion_jobs    (document_id -> resource_id; table name unchanged)

`citations.document_id` is NOT touched here: the citations table does not
exist yet (see 0001's docstring -- it is created by whichever future
migration mounts the chat router). The Citation ORM model
(app/models/citation.py) was already updated to define `resource_id`
pointing at `resources.id`, so that future migration will create the table
with this shape from the start; there is nothing here to migrate.

Portability: every ALTER uses `op.batch_alter_table(...)` so this runs
unchanged on both SQLite (local dev/tests) and PostgreSQL (Docker/prod) --
see app/db/session.py's documented dual-backend decision and alembic/env.py's
`render_as_batch=True`. Table renames use `op.rename_table`, which both
backends handle as a metadata-only operation (no data copy); PostgreSQL
additionally re-points existing foreign keys automatically on rename, and
SQLite (3.25+, i.e. every Python 3.11 bundled version) does the same by
default (`PRAGMA legacy_alter_table` is off) -- so the child tables' foreign
keys correctly reference `resources` once it exists, with no separate
constraint-fixup step required.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_resource_content_model"
down_revision: Union[str, None] = "0001_baseline_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- documents -> resources -------------------------------------------
    op.rename_table("documents", "resources")

    op.add_column(
        "resources",
        sa.Column("content_source", sa.String(length=20), nullable=False, server_default="file"),
    )
    op.add_column("resources", sa.Column("text_hash", sa.String(length=64), nullable=True))

    with op.batch_alter_table("resources") as batch_op:
        batch_op.alter_column("filename", existing_type=sa.String(length=512), nullable=True)
        batch_op.alter_column("storage_key", existing_type=sa.String(length=1024), nullable=True)
        batch_op.alter_column("mime_type", existing_type=sa.String(length=100), nullable=True)
        batch_op.alter_column("size_bytes", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("checksum", existing_type=sa.String(length=64), nullable=True)

    op.drop_index("ix_documents_workspace_id", table_name="resources")
    op.drop_index("ix_documents_checksum", table_name="resources")
    op.create_index("ix_resources_workspace_id", "resources", ["workspace_id"])
    op.create_index("ix_resources_checksum", "resources", ["checksum"])
    op.create_index("ix_resources_text_hash", "resources", ["text_hash"])

    # -- document_pages -> resource_pages ----------------------------------
    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    with op.batch_alter_table("document_pages") as batch_op:
        batch_op.alter_column("document_id", new_column_name="resource_id", existing_type=sa.String(length=36))
    op.rename_table("document_pages", "resource_pages")
    op.create_index("ix_resource_pages_resource_id", "resource_pages", ["resource_id"])

    # -- document_chunks -> resource_chunks ---------------------------------
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    with op.batch_alter_table("document_chunks") as batch_op:
        batch_op.alter_column("document_id", new_column_name="resource_id", existing_type=sa.String(length=36))
    op.rename_table("document_chunks", "resource_chunks")
    op.create_index("ix_resource_chunks_resource_id", "resource_chunks", ["resource_id"])

    # -- ingestion_jobs: column rename only, table name unchanged -----------
    op.drop_index("ix_ingestion_jobs_document_id", table_name="ingestion_jobs")
    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.alter_column("document_id", new_column_name="resource_id", existing_type=sa.String(length=36))
    op.create_index("ix_ingestion_jobs_resource_id", "ingestion_jobs", ["resource_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_resource_id", table_name="ingestion_jobs")
    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.alter_column("resource_id", new_column_name="document_id", existing_type=sa.String(length=36))
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])

    op.drop_index("ix_resource_chunks_resource_id", table_name="resource_chunks")
    op.rename_table("resource_chunks", "document_chunks")
    with op.batch_alter_table("document_chunks") as batch_op:
        batch_op.alter_column("resource_id", new_column_name="document_id", existing_type=sa.String(length=36))
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    op.drop_index("ix_resource_pages_resource_id", table_name="resource_pages")
    op.rename_table("resource_pages", "document_pages")
    with op.batch_alter_table("document_pages") as batch_op:
        batch_op.alter_column("resource_id", new_column_name="document_id", existing_type=sa.String(length=36))
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])

    op.drop_index("ix_resources_text_hash", table_name="resources")
    op.drop_index("ix_resources_checksum", table_name="resources")
    op.drop_index("ix_resources_workspace_id", table_name="resources")
    op.create_index("ix_documents_checksum", "resources", ["checksum"])
    op.create_index("ix_documents_workspace_id", "resources", ["workspace_id"])

    with op.batch_alter_table("resources") as batch_op:
        batch_op.alter_column("checksum", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("size_bytes", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("mime_type", existing_type=sa.String(length=100), nullable=False)
        batch_op.alter_column("storage_key", existing_type=sa.String(length=1024), nullable=False)
        batch_op.alter_column("filename", existing_type=sa.String(length=512), nullable=False)

    op.drop_column("resources", "text_hash")
    op.drop_column("resources", "content_source")

    op.rename_table("resources", "documents")
