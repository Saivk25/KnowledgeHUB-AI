from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK


class Answer(Base, UUIDPK):
    __tablename__ = "answers"

    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("messages.id"), index=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    retrieval_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OK")  # OK | INSUFFICIENT | ERROR

    # -- Milestone 8 (Local-First Retrieval & Provenance) -------------------
    # Provenance is structurally required alongside every answer (Architecture
    # Section 9 item 4), not computed ad hoc at display time -- these four
    # columns are the persisted, auditable record of what
    # services/sufficiency.py and services/retrieval_service.py decided for
    # this answer (DRR Section 16: log the sufficiency score and matched
    # evidence alongside every answer's provenance label).
    # LOCAL | HYBRID | EXTERNAL | None
    provenance: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sufficiency_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retrieval_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sufficiency_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # -- Milestone 9 (Intent Workflows) --------------------------------------
    # Every existing row predates this column and is a genuine EXPLAIN
    # answer (the only intent that existed before this milestone), hence
    # the default -- no backfill migration needed beyond the column default
    # itself. See app/schemas/intents.py's IntentType.
    intent: Mapped[str] = mapped_column(String(20), nullable=False, default="EXPLAIN")
    # Free-form JSON (stored as text, matching this codebase's existing
    # convention of using Text for JSON-shaped columns without a real
    # per-row schema -- see Resource.type_metadata's own precedent)
    # holding whatever structured detail doesn't fit the Citation table:
    # Compare's per-target sufficiency verdicts, Search's raw hit count
    # before truncation, etc. Null for intents that don't need it.
    intent_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    citations = relationship("Citation", back_populates="answer", cascade="all, delete-orphan")
