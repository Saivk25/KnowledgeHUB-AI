"""Milestone 11: confidence & correction UX (resource_corrections)

Revision ID: 0009_confidence_correction_ux
Revises: 0008_study_workflows
Create Date: 2026-07-23

One new table, purely additive -- no existing table's columns change
(see app/models/correction.py for the full design rationale and
docs/milestones/MILESTONE_11.md Section 4.1/4.9 for why a dedicated
correction-history table is needed rather than overloading an existing
one): `resource_corrections` logs one row per classification field
changed via PATCH /documents/{id}/classification, capturing the prior
value/confidence immediately before they are overwritten.

No backfill: this is new structure, not new columns on existing rows.
Every field this milestone otherwise surfaces (DocumentOut's auto_*
fields, AnswerOut/IntentResponse's sufficiencyReason) already exists on
Resource/Answer -- no other migration is needed for those.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_confidence_correction_ux"
down_revision: Union[str, None] = "0008_study_workflows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_corrections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("resource_id", sa.String(length=36), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("field", sa.String(length=20), nullable=False),
        sa.Column("previous_value", sa.String(length=200), nullable=True),
        sa.Column("previous_confidence", sa.Float(), nullable=True),
        sa.Column("new_value", sa.String(length=200), nullable=False),
        sa.Column("corrected_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_resource_corrections_resource_id", "resource_corrections", ["resource_id"])
    op.create_index("ix_resource_corrections_workspace_id", "resource_corrections", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_resource_corrections_workspace_id", table_name="resource_corrections")
    op.drop_index("ix_resource_corrections_resource_id", table_name="resource_corrections")
    op.drop_table("resource_corrections")
