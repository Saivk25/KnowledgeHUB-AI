"""
ResourceCorrection model (Milestone 11: Confidence & Correction UX).

Audit basis (docs/milestones/MILESTONE_11.md Section 4.1): grepping every
file in app/models/ turned up no audit/history/correction table anywhere in
the codebase, and PATCH /documents/{id}/classification
(api/v1/routes/documents.py's update_classification) overwrites
content_category/subject with no record of the prior value, prior
confidence, or when the change happened. This model is that missing
correction-history log -- purely additive, one new table, no changes to
Resource or any other existing table/column.

One row is inserted per changed field from inside the existing
update_classification route body, capturing the resource's field/value/
confidence *before* they are overwritten (see documents.py). A read-only
GET /documents/{id}/corrections route exposes this history, newest first.

`corrected_at` is a dedicated column (not TimestampMixin's `created_at`)
because "when the correction happened" is this row's one substantive
timestamp and deserves its own explicit name in the schema, matching this
codebase's existing precedent of naming domain-specific timestamps
distinctly from the generic `created_at` audit column (e.g.
QuizAttempt.graded_at, VivaSession.completed_at in app/models/study.py).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPK, TimestampMixin


class CorrectionField:
    """The two classification fields resource_corrections can log a
    correction against, mirroring ResourceContentCategory's plain-string
    enum style (app/models/resource.py). Scoped to classification only for
    this milestone -- see MILESTONE_11.md Section 6, Design Decision 4."""

    CONTENT_CATEGORY = "CONTENT_CATEGORY"
    SUBJECT = "SUBJECT"

    ALL = frozenset({CONTENT_CATEGORY, SUBJECT})


class ResourceCorrection(Base, UUIDPK, TimestampMixin):
    __tablename__ = "resource_corrections"

    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id"), index=True, nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, nullable=False
    )
    field: Mapped[str] = mapped_column(String(20), nullable=False)
    # The resource's value/confidence for `field` immediately before this
    # correction overwrote them. Nullable: a resource's first-ever
    # correction may follow a classification run that never set a value
    # (e.g. no subject detected), or may precede any automatic
    # classification at all.
    previous_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    previous_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_value: Mapped[str] = mapped_column(String(200), nullable=False)
    corrected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
