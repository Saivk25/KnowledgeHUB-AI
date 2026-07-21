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

Milestone 5 addition: `extraction_confidence` (nullable float). Added by
migration 0003 once Multi-Format Ingestion introduced a format (image OCR)
whose extraction confidence is genuinely less than 1.0 -- see the field's
own inline comment below and docs/adr/0012-multi-format-extraction.md.

Milestone 6 addition: `content_category`/`subject` (+ confidences +
`_confirmed` flags) and their `auto_*` counterparts (migration 0004). See
those fields' own inline comments and
docs/adr/0013-classification-confidence.md.

Milestone 7 addition: no new columns on Resource itself -- the concept
graph (migration 0005) lives in three new tables (see
app/models/concept.py). Resource only gains one new relationship,
`concept_links`, mirroring `pages`/`chunks`/`jobs`'s existing
cascade-delete pattern. See docs/adr/0014-concept-graph.md.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK, TimestampMixin


class ResourceStatus:
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class ResourceContentCategory:
    """Milestone 6: the fixed, non-configurable content-category taxonomy
    (per the approved design -- do not expand or make user-configurable in
    this milestone). Directly from the original PRD's FR-1 list of content
    categories layered on top of file formats. See
    docs/adr/0013-classification-confidence.md."""

    LECTURE = "LECTURE"
    ASSIGNMENT = "ASSIGNMENT"
    QUESTION_PAPER = "QUESTION_PAPER"
    LAB_MANUAL = "LAB_MANUAL"
    RESEARCH_PAPER = "RESEARCH_PAPER"
    PERSONAL_NOTE = "PERSONAL_NOTE"
    OTHER = "OTHER"

    ALL = frozenset({LECTURE, ASSIGNMENT, QUESTION_PAPER, LAB_MANUAL, RESEARCH_PAPER, PERSONAL_NOTE, OTHER})


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

    # Milestone 5: the extractor's own reported confidence for this
    # resource's extracted text (0.0-1.0). 1.0 for every deterministic
    # parser (PDF/DOCX/PPTX/TXT/MD/code); only image OCR ever reports below
    # 1.0, and always the OCR engine's real score (see
    # app/services/extraction.py, docs/adr/0012-multi-format-extraction.md).
    # Nullable: unset until extraction completes, same lifecycle as
    # text_hash. Surfaced in the API response as of Milestone 6 (see
    # api/v1/routes/documents.py's _to_out()).
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # -- Milestone 6 (Metadata, Classification & Confidence) ---------------
    # Two parallel layers, deliberately not one:
    #
    # 1. Authoritative/display fields (content_category, subject, and their
    #    confidences) -- what the API returns and the UI shows. Once the
    #    corresponding `_confirmed` flag is set (via PATCH
    #    /documents/{id}/classification), automatic (re)classification must
    #    never overwrite these again -- a user's correction is the ground
    #    truth from that point on.
    # 2. `auto_*` fields -- the most recent automatic classifier result,
    #    always overwritten on every (re)classification run regardless of
    #    confirmation state. This is deliberately NOT a "never reclassify
    #    after correction" lock: automatic classification keeps running and
    #    its output is preserved here for future evaluation/logging/
    #    "suggest an updated classification" workflows, without ever
    #    silently changing what the user sees. See
    #    docs/adr/0013-classification-confidence.md.
    content_category: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    content_category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_category_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subject_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    subject_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    auto_content_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    auto_content_category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    auto_subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    auto_subject_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    pages = relationship("ResourcePage", back_populates="resource", cascade="all, delete-orphan")
    chunks = relationship("ResourceChunk", back_populates="resource", cascade="all, delete-orphan")
    jobs = relationship("IngestionJob", back_populates="resource", cascade="all, delete-orphan")
    # Milestone 7: this resource's evidence links into the concept graph.
    # Cascades on resource delete (same pattern as pages/chunks/jobs above);
    # api/v1/routes/documents.py's delete_document() reads the affected
    # concept_ids *before* the cascade runs so it can run the orphan-check
    # (app/services/concept_graph.py's recompute_concept_usage()) after.
    concept_links = relationship("ResourceConcept", back_populates="resource", cascade="all, delete-orphan")


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
