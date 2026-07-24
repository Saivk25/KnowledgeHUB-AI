"""Milestone 12 (Section 12 addendum): concept-resolution concurrency fix

Revision ID: 0010_concept_dedup_unique_index
Revises: 0009_confidence_correction_ux
Create Date: 2026-07-24

Backs the exact-name dedup check in
app/services/concept_graph.py's resolve_concept() with a database-level
guarantee. Prior to this migration, uniqueness of (workspace_id,
normalized_name) among ACTIVE concepts was enforced only at the
application layer (see app/models/concept.py's docstring, now updated) --
a plain SELECT-then-INSERT with no atomicity guarantee. Two concurrent
BackgroundTask ingestion runs resolving the same concept name could both
pass the SELECT before either committed its INSERT, producing two ACTIVE
concepts with the same normalized_name -- see
docs/milestones/MILESTONE_12.md Section 12 for the full discovery and
rationale.

A partial unique index -- only over rows where status = 'ACTIVE' -- is
the minimal fix: it leaves MERGED/UNUSED rows free to share a
normalized_name with each other and with the current ACTIVE row (matching
resolve_concept()'s own `Concept.status == ConceptStatus.ACTIVE` filter,
so no existing status-lifecycle behavior changes), while making a second
concurrent ACTIVE row with the same name impossible at the database
level. Supported identically on SQLite (full test suite) and PostgreSQL
(production) via SQLAlchemy's dialect-specific partial-index kwargs.

No column changes. No data migration -- any already-duplicated ACTIVE
concepts from before this fix are not touched by this migration itself
(see MILESTONE_12.md Section 12.1 step 5: resolved via the existing
POST /concepts/{id}/merge endpoint on a per-workspace basis, not by this
migration).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0010_concept_dedup_unique_index"
down_revision: Union[str, None] = "0009_confidence_correction_ux"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_concepts_workspace_normalized_name_active"
_WHERE_CLAUSE = sa.text("status = 'ACTIVE'")


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        "concepts",
        ["workspace_id", "normalized_name"],
        unique=True,
        postgresql_where=_WHERE_CLAUSE,
        sqlite_where=_WHERE_CLAUSE,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="concepts")
