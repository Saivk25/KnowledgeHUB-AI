"""Milestone 5: add Resource.extraction_confidence

Revision ID: 0003_extraction_confidence
Revises: 0002_resource_content_model
Create Date: 2026-07-21

Adds a single nullable column, `extraction_confidence` (float), to
`resources`. Multi-Format Ingestion (Milestone 5) introduces the first
extractor whose confidence is genuinely less than 1.0 (image OCR via
pytesseract) -- every other extractor (PDF/DOCX/PPTX/TXT/MD/code) reports a
flat 1.0, so this column has no meaningful value for any row created before
this migration. Nullable, no backfill: existing resources simply have
`extraction_confidence IS NULL` until they are re-ingested, exactly the same
"populate going forward, don't retroactively compute" approach Milestone 4
took for `text_hash` (see 0002's docstring).

Portability: `op.batch_alter_table` for SQLite/PostgreSQL parity, same as
every other migration in this chain (see alembic/env.py's
`render_as_batch=True`).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_extraction_confidence"
down_revision: Union[str, None] = "0002_resource_content_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resources") as batch_op:
        batch_op.add_column(sa.Column("extraction_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("resources") as batch_op:
        batch_op.drop_column("extraction_confidence")
