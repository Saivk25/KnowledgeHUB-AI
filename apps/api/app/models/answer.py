from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK


class Answer(Base, UUIDPK):
    __tablename__ = "answers"

    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("messages.id"), index=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    retrieval_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OK")  # OK | NO_EVIDENCE | ERROR

    citations = relationship("Citation", back_populates="answer", cascade="all, delete-orphan")
