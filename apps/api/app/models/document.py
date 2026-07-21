from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK, TimestampMixin


class DocumentStatus:
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class Document(Base, UUIDPK, TimestampMixin):
    __tablename__ = "documents"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # index=True: every upload runs a duplicate-detection query filtered on
    # (workspace_id, checksum) -- see app/api/v1/routes/documents.py. Without
    # an index here, that's a full per-workspace scan on every upload.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DocumentStatus.QUEUED)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    jobs = relationship("IngestionJob", back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base, UUIDPK):
    __tablename__ = "document_pages"

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id"), index=True, nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document = relationship("Document", back_populates="pages")


class DocumentChunk(Base, UUIDPK):
    __tablename__ = "document_chunks"

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id"), index=True, nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_point_id: Mapped[str] = mapped_column(String(36), nullable=False)

    document = relationship("Document", back_populates="chunks")
