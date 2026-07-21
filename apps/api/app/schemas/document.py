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


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    nextCursor: str | None = None


class IngestionJobOut(BaseModel):
    step: str
    status: str
    errorCode: str | None = None


class DocumentDetailOut(BaseModel):
    document: DocumentOut
    processingJob: IngestionJobOut | None = None
