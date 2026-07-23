from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK


class Citation(Base, UUIDPK):
    __tablename__ = "citations"

    answer_id: Mapped[str] = mapped_column(String(36), ForeignKey("answers.id"), index=True, nullable=False)
    # Renamed from document_id (Milestone 4): the parent entity is now
    # Resource, not Document -- see app/models/resource.py. First given a
    # migration in Milestone 8 (0006_retrieval_provenance.py), which mounts
    # the chat router this table has always been shaped for.
    resource_id: Mapped[str] = mapped_column(String(36), ForeignKey("resources.id"), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(36), ForeignKey("resource_chunks.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    citation_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Milestone 9 (Intent Workflows): lets Compare (and concept-targeted
    # Summarize) attribute a citation to a specific side/source (e.g.
    # "Resource A", a concept's name) without a new table. Null for
    # Explain/Search/resource-targeted Summarize, where a citation only
    # ever belongs to the one answer as a whole.
    target_label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    answer = relationship("Answer", back_populates="citations")
