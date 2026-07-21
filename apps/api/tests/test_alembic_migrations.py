"""
Milestone 4: Alembic migration chain integrity. Milestone 5 extended
EXPECTED_RESOURCE_COLUMNS with `extraction_confidence` (migration
0003_extraction_confidence) -- see that migration's docstring. Milestone 6
extended it again with the ten classification/confidence columns (migration
0004_classification_metadata). Milestone 7 adds three new tables --
`concepts`, `resource_concepts`, `concept_relationships` (migration
0005_concept_graph) -- to EXPECTED_TABLES; no `resources` columns changed,
so EXPECTED_RESOURCE_COLUMNS is unchanged.

These tests exist because conftest.py's autouse fixture already runs
`alembic upgrade head` for every other test in this suite (see conftest.py's
Milestone 4 note) -- that gives broad coverage that migrations produce a
schema the app can run against, but it always starts from empty and never
exercises downgrade(), never checks for schema drift against the ORM models,
and never checks the "existing create_all deployment" stamping path called
out in 0001_baseline_schema.py's docstring. This module covers those three
gaps explicitly, against its own throwaway SQLite file (not the shared
per-test engine from conftest.py).
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command
from alembic.config import Config

_ALEMBIC_INI = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")

# Tables a fresh `alembic upgrade head` is expected to create as of
# Milestone 4. Deliberately excludes conversations/messages/answers/
# citations -- see 0001_baseline_schema.py's docstring for why those are not
# created yet.
EXPECTED_TABLES = {
    "users",
    "workspaces",
    "resources",
    "resource_pages",
    "resource_chunks",
    "ingestion_jobs",
    # Milestone 7 (Concept Graph, migration 0005_concept_graph):
    "concepts",
    "resource_concepts",
    "concept_relationships",
    "alembic_version",
}

EXPECTED_RESOURCE_COLUMNS = {
    "id",
    "created_at",
    "workspace_id",
    "content_source",
    "filename",
    "storage_key",
    "mime_type",
    "size_bytes",
    "checksum",
    "text_hash",
    "page_count",
    "status",
    "error_message",
    "extraction_confidence",
    "content_category",
    "content_category_confidence",
    "content_category_confirmed",
    "subject",
    "subject_confidence",
    "subject_confirmed",
    "auto_content_category",
    "auto_content_category_confidence",
    "auto_subject",
    "auto_subject_confidence",
}

NULLABLE_RESOURCE_COLUMNS = {
    "filename",
    "storage_key",
    "mime_type",
    "size_bytes",
    "checksum",
    "text_hash",
    "extraction_confidence",
    "content_category",
    "content_category_confidence",
    "subject",
    "subject_confidence",
    "auto_content_category",
    "auto_content_category_confidence",
    "auto_subject",
    "auto_subject_confidence",
}

# content_category_confirmed / subject_confirmed are NOT NULL (default
# False) -- deliberately excluded from NULLABLE_RESOURCE_COLUMNS.


@pytest.fixture
def scratch_db_url(tmp_path):
    db_path = tmp_path / "migration_scratch.db"
    return f"sqlite:///{db_path}"


def _alembic_config(db_url: str) -> Config:
    cfg = Config(_ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_head_from_empty_creates_expected_schema(scratch_db_url):
    """A brand-new database (new dev machine, CI, fresh Docker volume) must
    reach the full Milestone 4 schema with a single `alembic upgrade head`
    -- no manual stamping required (see docstring's distinction between this
    case and the "existing create_all deployment" case below)."""
    cfg = _alembic_config(scratch_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(scratch_db_url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == EXPECTED_TABLES

    resource_columns = {c["name"] for c in inspector.get_columns("resources")}
    assert resource_columns == EXPECTED_RESOURCE_COLUMNS

    columns_by_name = {c["name"]: c for c in inspector.get_columns("resources")}
    for name in NULLABLE_RESOURCE_COLUMNS:
        assert columns_by_name[name]["nullable"] is True, f"{name} should be nullable"
    assert columns_by_name["content_source"]["nullable"] is False
    assert columns_by_name["workspace_id"]["nullable"] is False

    resource_chunk_columns = {c["name"] for c in inspector.get_columns("resource_chunks")}
    assert "resource_id" in resource_chunk_columns
    assert "document_id" not in resource_chunk_columns

    ingestion_job_columns = {c["name"] for c in inspector.get_columns("ingestion_jobs")}
    assert "resource_id" in ingestion_job_columns
    assert "document_id" not in ingestion_job_columns


def test_downgrade_to_base_and_upgrade_again_round_trips(scratch_db_url):
    """Every migration in this chain must be reversible -- proves
    downgrade() is not just decorative, and that re-upgrading after a full
    downgrade reproduces the same schema (catches asymmetric up/down bugs
    that a downgrade-never-tested chain tends to accumulate)."""
    cfg = _alembic_config(scratch_db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(scratch_db_url)
    inspector = inspect(engine)
    remaining = set(inspector.get_table_names()) - {"alembic_version"}
    assert remaining == set(), f"downgrade to base left tables behind: {remaining}"

    command.upgrade(cfg, "head")
    inspector = inspect(create_engine(scratch_db_url))
    assert set(inspector.get_table_names()) == EXPECTED_TABLES


def test_stamping_baseline_then_upgrading_matches_fresh_upgrade(scratch_db_url):
    """Simulates the documented path for an existing pre-Alembic deployment
    (0001_baseline_schema.py's docstring): manually create the Milestone 3
    schema (what create_all already built there), `alembic stamp
    0001_baseline_schema` instead of running 0001's SQL, then `alembic
    upgrade head` should apply only 0002 onward and land on the identical
    schema a fresh `upgrade head` produces."""
    engine = create_engine(scratch_db_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, created_at DATETIME, "
                "email VARCHAR(255) NOT NULL)"
            )
        )
        connection.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
        connection.execute(
            text(
                "CREATE TABLE workspaces ("
                "id VARCHAR(36) PRIMARY KEY, created_at DATETIME, "
                "owner_user_id VARCHAR(36) NOT NULL, name VARCHAR(255) NOT NULL"
                ")"
            )
        )
        connection.execute(text("CREATE INDEX ix_workspaces_owner_user_id ON workspaces (owner_user_id)"))
        connection.execute(
            text(
                "CREATE TABLE documents ("
                "id VARCHAR(36) PRIMARY KEY, created_at DATETIME, workspace_id VARCHAR(36) NOT NULL, "
                "filename VARCHAR(512) NOT NULL, storage_key VARCHAR(1024) NOT NULL, "
                "mime_type VARCHAR(100) NOT NULL, size_bytes INTEGER NOT NULL, "
                "checksum VARCHAR(64) NOT NULL, page_count INTEGER NOT NULL, "
                "status VARCHAR(20) NOT NULL, error_message TEXT"
                ")"
            )
        )
        connection.execute(text("CREATE INDEX ix_documents_workspace_id ON documents (workspace_id)"))
        connection.execute(text("CREATE INDEX ix_documents_checksum ON documents (checksum)"))
        connection.execute(
            text(
                "CREATE TABLE document_pages ("
                "id VARCHAR(36) PRIMARY KEY, document_id VARCHAR(36) NOT NULL, "
                "page_number INTEGER NOT NULL, text_content TEXT NOT NULL, char_count INTEGER NOT NULL"
                ")"
            )
        )
        connection.execute(text("CREATE INDEX ix_document_pages_document_id ON document_pages (document_id)"))
        connection.execute(
            text(
                "CREATE TABLE document_chunks ("
                "id VARCHAR(36) PRIMARY KEY, document_id VARCHAR(36) NOT NULL, "
                "page_number INTEGER NOT NULL, chunk_index INTEGER NOT NULL, content TEXT NOT NULL, "
                "content_hash VARCHAR(64) NOT NULL, vector_point_id VARCHAR(36) NOT NULL"
                ")"
            )
        )
        connection.execute(
            text("CREATE INDEX ix_document_chunks_document_id ON document_chunks (document_id)")
        )
        connection.execute(
            text(
                "CREATE TABLE ingestion_jobs ("
                "id VARCHAR(36) PRIMARY KEY, document_id VARCHAR(36) NOT NULL, status VARCHAR(20) NOT NULL, "
                "step VARCHAR(20) NOT NULL, attempt_count INTEGER NOT NULL, error_code TEXT, "
                "started_at DATETIME, completed_at DATETIME"
                ")"
            )
        )
        connection.execute(text("CREATE INDEX ix_ingestion_jobs_document_id ON ingestion_jobs (document_id)"))

    cfg = _alembic_config(scratch_db_url)
    command.stamp(cfg, "0001_baseline_schema")
    command.upgrade(cfg, "head")

    inspector = inspect(create_engine(scratch_db_url))
    assert set(inspector.get_table_names()) == EXPECTED_TABLES
    assert {c["name"] for c in inspector.get_columns("resources")} == EXPECTED_RESOURCE_COLUMNS
