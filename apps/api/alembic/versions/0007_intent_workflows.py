"""Milestone 9: intent workflows (Explain, Compare, Summarize, Search)

Revision ID: 0007_intent_workflows
Revises: 0006_retrieval_provenance
Create Date: 2026-07-23

Adds three columns, no new tables -- Compare and Summarize read existing
resource/concept/chunk data, they don't need new graph structure (see
docs/milestones/MILESTONE_9.md Section 3.5):

1. `answers.intent` (String(20), NOT NULL, default "EXPLAIN") -- every
   existing row predates this milestone and is a genuine Explain answer
   (the only intent that existed before now), so the default needs no
   separate backfill statement.
2. `answers.intent_payload` (Text, nullable) -- structured per-intent
   extras that don't fit the `citations` table (Compare's per-target
   sufficiency verdicts, Search's raw hit count before truncation).
3. `citations.target_label` (String(100), nullable) -- lets Compare (and
   concept-targeted Summarize) attribute a citation to a specific side/
   source without a new table.

`op.batch_alter_table` for both, matching 0004_classification_metadata.py
and 0006_retrieval_provenance.py's precedent for altering an existing
table on SQLite/PostgreSQL.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_intent_workflows"
down_revision: Union[str, None] = "0006_retrieval_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("answers") as batch_op:
        batch_op.add_column(
            sa.Column("intent", sa.String(length=20), nullable=False, server_default="EXPLAIN")
        )
        batch_op.add_column(sa.Column("intent_payload", sa.Text(), nullable=True))

    with op.batch_alter_table("citations") as batch_op:
        batch_op.add_column(sa.Column("target_label", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("citations") as batch_op:
        batch_op.drop_column("target_label")

    with op.batch_alter_table("answers") as batch_op:
        batch_op.drop_column("intent_payload")
        batch_op.drop_column("intent")
