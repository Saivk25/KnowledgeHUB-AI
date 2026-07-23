"""Milestone 10: study workflows (Quiz me, Flashcards, Viva mode, Revision mode, Study planner)

Revision ID: 0008_study_workflows
Revises: 0007_intent_workflows
Create Date: 2026-07-23

Two new tables, purely additive -- no existing table's columns change
(see app/models/study.py for the full design rationale and
docs/milestones/MILESTONE_10.md Section 3.3 for why these two need real
server-side-only state rather than reusing Answer.intent_payload the way
Compare/Search do):

1. `quiz_attempts` -- Quiz me's generate-then-grade round trip. Holds the
   full answer key in `questions_payload`, never serialized to the client
   as-is.
2. `viva_sessions` -- Viva mode's multi-turn conversation. Holds the full
   turn-by-turn transcript including each turn's grading rubric in
   `transcript_payload`, same reasoning as above.

No backfill: this is new structure, not new columns on existing rows.
Portability: plain `op.create_table`, same as 0005_concept_graph.py's
precedent for brand-new tables (`op.batch_alter_table` is only needed
when altering an existing table on SQLite, not when creating one).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_study_workflows"
down_revision: Union[str, None] = "0007_intent_workflows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("resource_id", sa.String(length=36), sa.ForeignKey("resources.id"), nullable=True),
        sa.Column("concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=True),
        sa.Column("target_label", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("questions_payload", sa.Text(), nullable=False),
        sa.Column("graded_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_quiz_attempts_workspace_id", "quiz_attempts", ["workspace_id"])

    op.create_table(
        "viva_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("resource_id", sa.String(length=36), sa.ForeignKey("resources.id"), nullable=True),
        sa.Column("concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=True),
        sa.Column("target_label", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("max_turns", sa.Integer(), nullable=False),
        sa.Column("transcript_payload", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_viva_sessions_workspace_id", "viva_sessions", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_viva_sessions_workspace_id", table_name="viva_sessions")
    op.drop_table("viva_sessions")

    op.drop_index("ix_quiz_attempts_workspace_id", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
