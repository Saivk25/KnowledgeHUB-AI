from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK


class Citation(Base, UUIDPK):
    __tablename__ = "citations"

    answer_id: Mapped[str] = mapped_column(String(36), ForeignKey("answers.id"), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_chunks.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    citation_order: Mapped[int] = mapped_column(Integer, nullable=False)

    answer = relationship("Answer", back_populates="citations")
