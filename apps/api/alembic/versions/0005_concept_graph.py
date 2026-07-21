"""Milestone 7: concept graph (concepts, resource_concepts, concept_relationships)

Revision ID: 0005_concept_graph
Revises: 0004_classification_metadata
Create Date: 2026-07-22

Three new tables, purely additive -- no existing table's columns change
(see app/models/concept.py for the full design rationale, and
docs/adr/0014-concept-graph.md for the approved-design decisions this
migration implements):

1. `concepts` -- a first-class knowledge object per workspace. Uniqueness
   of (workspace_id, normalized_name) among ACTIVE concepts is enforced at
   the application layer (app/services/concept_graph.py's
   `resolve_concept`), not a DB constraint -- matching this codebase's
   existing convention (see resource.py's own docstring on `checksum`).
2. `resource_concepts` -- the evidence link (resource -> concept), with a
   required (`NOT NULL`) `evidence_chunk_id`: every evidence link must
   point at the specific chunk that supports it.
3. `concept_relationships` -- a typed, directed edge between two concepts,
   also with a required `evidence_chunk_id` -- per the approved design,
   no relationship is ever stored without a supporting evidence pointer.

No backfill: this is new structure, not new columns on existing rows --
there is nothing to backfill. Portability: plain `op.create_table`, same
as every other "brand new table" migration in this chain (see
0001_baseline_schema.py); `op.batch_alter_table` is only needed when
altering an existing table on SQLite, not when creating a new one.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_concept_graph"
down_revision: Union[str, None] = "0004_classification_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "concepts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "merged_into_concept_id",
            sa.String(length=36),
            sa.ForeignKey("concepts.id"),
            nullable=True,
        ),
        sa.Column(
            "possible_duplicate_of_concept_id",
            sa.String(length=36),
            sa.ForeignKey("concepts.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_concepts_workspace_id", "concepts", ["workspace_id"])
    op.create_index("ix_concepts_normalized_name", "concepts", ["normalized_name"])

    op.create_table(
        "resource_concepts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("resource_id", sa.String(length=36), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("contribution_type", sa.String(length=20), nullable=False),
        sa.Column(
            "evidence_chunk_id", sa.String(length=36), sa.ForeignKey("resource_chunks.id"), nullable=False
        ),
    )
    op.create_index("ix_resource_concepts_resource_id", "resource_concepts", ["resource_id"])
    op.create_index("ix_resource_concepts_concept_id", "resource_concepts", ["concept_id"])

    op.create_table(
        "concept_relationships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("from_concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=False),
        sa.Column("to_concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=False),
        sa.Column("relationship_type", sa.String(length=20), nullable=False),
        sa.Column("strength", sa.Float(), nullable=True),
        sa.Column(
            "evidence_chunk_id", sa.String(length=36), sa.ForeignKey("resource_chunks.id"), nullable=False
        ),
    )
    op.create_index("ix_concept_relationships_workspace_id", "concept_relationships", ["workspace_id"])
    op.create_index("ix_concept_relationships_from_concept_id", "concept_relationships", ["from_concept_id"])
    op.create_index("ix_concept_relationships_to_concept_id", "concept_relationships", ["to_concept_id"])


def downgrade() -> None:
    op.drop_index("ix_concept_relationships_to_concept_id", table_name="concept_relationships")
    op.drop_index("ix_concept_relationships_from_concept_id", table_name="concept_relationships")
    op.drop_index("ix_concept_relationships_workspace_id", table_name="concept_relationships")
    op.drop_table("concept_relationships")

    op.drop_index("ix_resource_concepts_concept_id", table_name="resource_concepts")
    op.drop_index("ix_resource_concepts_resource_id", table_name="resource_concepts")
    op.drop_table("resource_concepts")

    op.drop_index("ix_concepts_normalized_name", table_name="concepts")
    op.drop_index("ix_concepts_workspace_id", table_name="concepts")
    op.drop_table("concepts")
