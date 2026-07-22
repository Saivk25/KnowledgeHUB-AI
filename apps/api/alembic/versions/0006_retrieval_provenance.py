"""Milestone 8: retrieval provenance (conversations, messages, answers, citations)

Revision ID: 0006_retrieval_provenance
Revises: 0005_concept_graph
Create Date: 2026-07-22

Mounts the chat router (app/api/v1/routes/chat.py) for the first time --
this is the migration referenced by app/models/citation.py's own comment
and by tests/test_alembic_migrations.py's EXPECTED_TABLES, which has never
listed these four tables until now (see app/models/conversation.py,
answer.py, citation.py -- all already correctly shaped since Milestone 4,
dormant purely because no migration created them; see
docs/adr/0003-retrieval-pipeline-scope.md and
docs/adr/0004-ai-provider-strategy.md).

Four brand-new tables (plain `op.create_table`, same as every other
"brand new table" migration in this chain -- see 0005_concept_graph.py's
own docstring on why `op.batch_alter_table` is unneeded here):

1. `conversations` -- one per chat thread, scoped to (workspace_id, user_id).
2. `messages` -- user/assistant turns within a conversation.
3. `answers` -- one per assistant message. Milestone 8 adds four columns
   beyond the dormant Milestone-4 shape: `provenance`, `sufficiency_score`,
   `retrieval_confidence`, `sufficiency_reason` -- the persisted, auditable
   record of what app/services/sufficiency.py decided for this answer (DRR
   Section 16; Architecture Section 9 item 4: provenance is structurally
   required, not bolted on after the fact).
4. `citations` -- one per cited chunk within an answer.

Also alters the existing `workspaces` table (Milestone 2), adding
`allow_external_fallback` (`NOT NULL DEFAULT false`) -- the workspace-level
consent gate for answering from general knowledge when local evidence is
insufficient (approved design, decision 4). `op.batch_alter_table` is used
here, matching 0004_classification_metadata.py's precedent for altering an
existing table on SQLite/PostgreSQL.

No backfill needed for the new tables (nothing existed to backfill).
`allow_external_fallback` defaults every existing workspace to False --
the safe, no-external-call-without-consent default the approved design
requires.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_retrieval_provenance"
down_revision: Union[str, None] = "0005_concept_graph"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_conversations_workspace_id", "conversations", ["workspace_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "answers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("message_id", sa.String(length=36), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=False),
        sa.Column("generation_latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provenance", sa.String(length=20), nullable=True),
        sa.Column("sufficiency_score", sa.Float(), nullable=False),
        sa.Column("retrieval_confidence", sa.Float(), nullable=False),
        sa.Column("sufficiency_reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_answers_message_id", "answers", ["message_id"])

    op.create_table(
        "citations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("answer_id", sa.String(length=36), sa.ForeignKey("answers.id"), nullable=False),
        sa.Column("resource_id", sa.String(length=36), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("resource_chunks.id"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("citation_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_citations_answer_id", "citations", ["answer_id"])

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(
            sa.Column("allow_external_fallback", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_column("allow_external_fallback")

    op.drop_index("ix_citations_answer_id", table_name="citations")
    op.drop_table("citations")

    op.drop_index("ix_answers_message_id", table_name="answers")
    op.drop_table("answers")

    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversations_workspace_id", table_name="conversations")
    op.drop_table("conversations")
