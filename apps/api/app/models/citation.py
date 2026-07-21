from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK


class Citation(Base, UUIDPK):
    __tablename__ = "citations"

    answer_id: Mapped[str] = mapped_column(String(36), ForeignKey("answers.id"), index=True, nullable=False)
    # Renamed from document_id (Milestone 4): the parent entity is now
    # Resource, not Document -- see app/models/resource.py. This table is
    # still dormant (not mounted; see app/api/v1/router.py), so no migration
    # creates it yet -- whichever future milestone mounts the chat router
    # will create it with this (already-correct) shape.
    resource_id: Mapped[str] = mapped_column(String(36), ForeignKey("resources.id"), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(36), ForeignKey("resource_chunks.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    citation_order: Mapped[int] = mapped_column(Integer, nullable=False)

    answer = relationship("Answer", back_populates="citations")
