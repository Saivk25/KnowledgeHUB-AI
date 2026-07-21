"""
Resource model (Milestone 4).

Replaces the Milestone 3 `Document` model (see the deleted
app/models/document.py; git history retains it). This is a rename-and-extend,
not a parallel entity: the Design Readiness Review scoped Milestone 4 to
evolve `documents` into `resources` now, specifically so the schema does not
have to be migrated a second time once non-PDF file types (DOCX, images,
YouTube transcripts, etc. -- see the roadmap) and fileless capture (quick
notes, pasted text, URLs -- see Product Philosophy #4, "Capture must be as
important as Retrieval") land in later milestones.

What changed vs. Document, and why:

1. `content_source` discriminator (ResourceContentSource.FILE | CAPTURE).
   FILE means "backed by an uploaded file" (the only path any code actually
   builds today -- PDF upload, per Milestone 3). CAPTURE means "fileless"
   (pasted text, quick note, URL, etc.) -- no ingestion pipeline for CAPTURE
   exists yet; that is out of this milestone's approved scope. The column
   exists now purely so the later milestone that adds capture ingestion does
   not need its own schema migration.

2. Nullable storage fields (filename, storage_key, mime_type, size_bytes,
   checksum). All five are still populated together for every FILE resource,
   exactly as Document required NOT NULL for them -- nothing about the
   Milestone 3 upload path's guarantees changes. They are nullable at the
   schema level only so a future CAPTURE resource (no underlying file) is
   representable without a second migration. This is enforced at the
   application layer (the upload route always sets all five), not by a CHECK
   constraint, matching this codebase's existing style of keeping
   cross-field invariants in Python rather than SQL (see e.g. the workspace
   tenant-boundary comment in models/workspace.py).

3. `text_hash` -- content-level dedup, independent of the file's raw bytes.
   `checksum` (byte-identical dedup) is unchanged and still checked on every
   upload (see api/v1/routes/documents.py). `text_hash` is new: it is a
   sha256 of the resource's extracted/captured text, populated once that text
   is known (at the end of extraction for FILE resources -- see
   services/ingestion_service.py; immediately at creation time for CAPTURE
   resources, once that path exists). It lets two resources with different
   bytes but the same underlying content (a re-exported PDF, or a pasted note
   that duplicates an already-uploaded file) eventually be recognized as
   evidence for the same knowledge (Product Philosophy #2). This migration
   only *populates* the column -- it does not add a new rejection/duplicate
   error path, since turning a duplicate-content signal into a blocking
   product behavior is a product decision outside this milestone's approved
   scope (schema + Alembic only).
"""

from __future__ import annotations

import hashlib

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK, TimestampMixin


class ResourceStatus:
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class ResourceContentSource:
    """Discriminator: what produced this resource.

    FILE -- an uploaded file (PDF today; other file types are later
    milestones per the roadmap). CAPTURE -- fileless content (pasted text,
    quick note, URL, etc.). Only FILE has an implemented ingestion path as
    of this milestone.
    """

    FILE = "file"
    CAPTURE = "capture"


def compute_text_hash(text: str) -> str:
    """
    Sha256 of normalized text content, used for content-level (not
    byte-level) deduplication. Normalization is deliberately minimal
    (strip + collapse-nothing) so it stays a pure function of "the text
    this resource contributes," matching the sha256-of-bytes convention
    already used for `checksum` (services/storage.py) and chunk
    `content_hash` (services/chunking.py).
    """

    normalized = text.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class Resource(Base, UUIDPK, TimestampMixin):
    __tablename__ = "resources"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, nullable=False
    )

    content_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ResourceContentSource.FILE
    )

    # -- File-backed storage fields. NULL for CAPTURE resources (no file).
    # For every FILE resource these four are populated together at creation
    # time (see api/v1/routes/documents.py) -- unchanged from Document.
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # index=True: every upload runs a duplicate-detection query filtered on
    # (workspace_id, checksum) -- see app/api/v1/routes/documents.py. Nullable
    # because CAPTURE resources have no file bytes to hash.
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # index=True: content-level dedup, see module docstring above. Nullable
    # until the resource's text is known (post-extraction for FILE, at
    # creation for CAPTURE).
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ResourceStatus.QUEUED)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    pages = relationship("ResourcePage", back_populates="resource", cascade="all, delete-orphan")
    chunks = relationship("ResourceChunk", back_populates="resource", cascade="all, delete-orphan")
    jobs = relationship("IngestionJob", back_populates="resource", cascade="all, delete-orphan")


class ResourcePage(Base, UUIDPK):
    __tablename__ = "resource_pages"

    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id"), index=True, nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    resource = relationship("Resource", back_populates="pages")


class ResourceChunk(Base, UUIDPK):
    __tablename__ = "resource_chunks"

    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id"), index=True, nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_point_id: Mapped[str] = mapped_column(String(36), nullable=False)

    resource = relationship("Resource", back_populates="chunks")
