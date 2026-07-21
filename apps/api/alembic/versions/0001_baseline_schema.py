"""Baseline: schema as produced by Base.metadata.create_all through Milestone 3

Revision ID: 0001_baseline_schema
Revises:
Create Date: 2026-07-21

This revision exists to give Alembic a starting point that matches what
Base.metadata.create_all(bind=engine) has been building on every API startup
since Milestone 1 (see the removed call in app/main.py and
docs/adr/0008-schema-create-all-not-alembic.md, superseded by
docs/adr/0010-alembic-migrations.md). It intentionally creates ONLY the
tables that a running instance actually has today: users, workspaces,
documents (+ document_pages, document_chunks), and ingestion_jobs.

It deliberately does NOT create conversations / messages / answers /
citations. Those models exist in app/models/ but, as of Milestone 3, are
never imported by anything on the live request path (app.api.v1.router
intentionally excludes chat.py -- see that file's docstring), so
create_all has in fact never created them in any real deployment. Building
them here would be pre-building schema for a feature this milestone was not
asked to touch. Whichever future milestone mounts the chat router adds its
own revision creating those tables at that point -- the same "a milestone's
footprint arrives in the commit that activates it" convention already
documented in app/README.md for requirements.txt.

Deployment note (existing environments): if you are applying this migration
chain to a database that Base.metadata.create_all already built (i.e. any
environment that ran Milestone 1-3 before Alembic existed), do NOT run
`alembic upgrade head` directly -- these CREATE TABLE statements will
collide with tables that already exist. Instead run `alembic stamp 0001_baseline_schema`
first (marks this revision as already applied without running its SQL),
then `alembic upgrade head` to apply only 0002 onward. For a fresh database
(new local dev setup, CI, a fresh Docker volume), `alembic upgrade head` from
empty is correct and needs no stamping.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_workspaces_owner_user_id", "workspaces", ["owner_user_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])
    op.create_index("ix_documents_checksum", "documents", ["checksum"])

    op.create_table(
        "document_pages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("vector_point_id", sa.String(length=36), nullable=False),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("step", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_document_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    op.drop_table("document_pages")

    op.drop_index("ix_documents_checksum", table_name="documents")
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_workspaces_owner_user_id", table_name="workspaces")
    op.drop_table("workspaces")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
