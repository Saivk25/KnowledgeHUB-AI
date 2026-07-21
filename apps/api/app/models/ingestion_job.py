from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK


class IngestionStep:
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    # Milestone 6: classification (content category + subject suggestion)
    # runs once extraction produces the resource's full text, before
    # chunking/embedding/indexing. A classifier failure never lands here as
    # FAILED -- see app/services/classification.py and
    # app/services/ingestion_service.py's graceful-degradation handling.
    CLASSIFYING = "CLASSIFYING"
    INDEXING = "INDEXING"
    # Milestone 7: concept-linking runs after indexing (it needs the
    # resource's chunks and their vectors to already exist -- evidence
    # links point at specific chunks, and dedup matching runs an ANN
    # search that only makes sense once this resource's own vectors are
    # indexed) and before DONE. Same graceful-degradation rule as
    # CLASSIFYING: a concept-linking failure never lands here as FAILED --
    # see app/services/concept_linking.py, app/services/concept_graph.py,
    # and app/services/ingestion_service.py.
    CONCEPT_LINKING = "CONCEPT_LINKING"
    DONE = "DONE"
    FAILED = "FAILED"


class IngestionJob(Base, UUIDPK):
    __tablename__ = "ingestion_jobs"

    # Renamed from document_id (Milestone 4): the parent entity is now
    # Resource, not Document -- see app/models/resource.py.
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    step: Mapped[str] = mapped_column(String(20), nullable=False, default=IngestionStep.UPLOADED)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    resource = relationship("Resource", back_populates="jobs")
