from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK, TimestampMixin


class Workspace(Base, UUIDPK, TimestampMixin):
    """
    MVP: one personal workspace per user. This is the tenant boundary used
    to filter every document, chunk, and citation query. The schema does not
    prevent multi-member workspaces later (Phase 2 adds a memberships table).
    """

    __tablename__ = "workspaces"

    # index=True: every protected request looks up "the current user's
    # workspace" via get_current_workspace() filtering on this column
    # (see app/deps.py). Without an index this is a full table scan per
    # request once the table has more than a handful of rows.
    owner_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="My Workspace")

    # Milestone 8 (Local-First Retrieval & Provenance): consent for
    # retrieval_service to answer from general knowledge when local
    # evidence is insufficient, without requiring per-request confirmation
    # every time. Defaults to False -- an external model is never called
    # without either this being explicitly enabled or explicit per-request
    # confirmation (approved design, decision 4). Not yet exposed through
    # any API response or settings UI (the approved M8 design scoped the
    # UI to exactly three additions, none of which was a settings toggle
    # for this) -- reachable only by a direct write today, same as this
    # milestone's own tests do. Expose via PATCH /workspace whenever a
    # future milestone actually needs a UI for it.
    allow_external_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    owner = relationship("User", back_populates="workspaces")
