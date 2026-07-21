"""Milestone 6: add classification & confidence metadata to Resource

Revision ID: 0004_classification_metadata
Revises: 0003_extraction_confidence
Create Date: 2026-07-22

Adds ten nullable columns to `resources`, in two parallel layers (see
app/models/resource.py's own comments for the full rationale):

1. Authoritative/display: `content_category`, `content_category_confidence`,
   `content_category_confirmed` (bool, NOT NULL default False), `subject`,
   `subject_confidence`, `subject_confirmed` (bool, NOT NULL default False).
   `content_category` is indexed for future "browse/filter by category"
   queries.
2. Latest-automatic-result (always overwritten, independent of the
   `_confirmed` flags above): `auto_content_category`,
   `auto_content_category_confidence`, `auto_subject`,
   `auto_subject_confidence`.

No backfill: every resource created before this migration simply has all
ten columns NULL/False until it is next (re)ingested -- the same
"populate going forward" approach Milestones 4 and 5 took for `text_hash`
and `extraction_confidence`.

Portability: `op.batch_alter_table` for SQLite/PostgreSQL parity, matching
every migration in this chain.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_classification_metadata"
down_revision: Union[str, None] = "0003_extraction_confidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resources") as batch_op:
        batch_op.add_column(sa.Column("content_category", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("content_category_confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "content_category_confirmed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("subject", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("subject_confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("subject_confirmed", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("auto_content_category", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("auto_content_category_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("auto_subject", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("auto_subject_confidence", sa.Float(), nullable=True))

    op.create_index("ix_resources_content_category", "resources", ["content_category"])


def downgrade() -> None:
    op.drop_index("ix_resources_content_category", table_name="resources")
    with op.batch_alter_table("resources") as batch_op:
        batch_op.drop_column("auto_subject_confidence")
        batch_op.drop_column("auto_subject")
        batch_op.drop_column("auto_content_category_confidence")
        batch_op.drop_column("auto_content_category")
        batch_op.drop_column("subject_confirmed")
        batch_op.drop_column("subject_confidence")
        batch_op.drop_column("subject")
        batch_op.drop_column("content_category_confirmed")
        batch_op.drop_column("content_category_confidence")
        batch_op.drop_column("content_category")
