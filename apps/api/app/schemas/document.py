from pydantic import BaseModel


class YoutubeIngestRequest(BaseModel):
    """Milestone 5: POST /documents/youtube body. See
    app/services/youtube.py for URL validation (restricted to
    youtube.com/youtu.be video-ID shapes, not an arbitrary URL fetch)."""

    url: str


class DocumentOut(BaseModel):
    id: str
    filename: str
    status: str
    pageCount: int
    sizeBytes: int
    errorMessage: str | None = None
    createdAt: str
    # Milestone 6: extraction confidence (Milestone 5 field, first surfaced
    # here) + classification metadata. See app/models/resource.py and
    # docs/adr/0013-classification-confidence.md.
    extractionConfidence: float | None = None
    contentCategory: str | None = None
    contentCategoryConfidence: float | None = None
    contentCategoryConfirmed: bool = False
    subject: str | None = None
    subjectConfidence: float | None = None
    subjectConfirmed: bool = False
    # Milestone 11 (Confidence & Correction UX): the most recent automatic
    # classification run, regardless of whether content_category/subject
    # have since been confirmed -- exposes Resource.auto_* (written on
    # every classification run by ingestion_service.py's
    # _apply_classification, previously never reaching the API at all).
    # See docs/milestones/MILESTONE_11.md Section 4.2.
    autoContentCategory: str | None = None
    autoContentCategoryConfidence: float | None = None
    autoSubject: str | None = None
    autoSubjectConfidence: float | None = None


class ClassificationUpdateRequest(BaseModel):
    """Milestone 6: PATCH /documents/{id}/classification body. At least one
    of the two fields must be provided (enforced in the route, not here,
    to produce a clear 422 error code rather than a generic validation
    error)."""

    contentCategory: str | None = None
    subject: str | None = None


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    nextCursor: str | None = None


class IngestionJobOut(BaseModel):
    step: str
    status: str
    errorCode: str | None = None


class ConceptLinkOut(BaseModel):
    """Milestone 7: one of this document's evidence links into the concept
    graph, surfaced on the detail response only (not the list response --
    see DocumentDetailOut below)."""

    conceptId: str
    name: str
    contributionType: str
    confidence: float


class DocumentDetailOut(BaseModel):
    document: DocumentOut
    processingJob: IngestionJobOut | None = None
    concepts: list[ConceptLinkOut] = []


class CorrectionOut(BaseModel):
    """Milestone 11: one row of a document's correction history. See
    GET /documents/{id}/corrections and app/models/correction.py."""

    id: str
    field: str  # CONTENT_CATEGORY | SUBJECT
    previousValue: str | None = None
    previousConfidence: float | None = None
    newValue: str
    correctedAt: str


class CorrectionListOut(BaseModel):
    items: list[CorrectionOut]
