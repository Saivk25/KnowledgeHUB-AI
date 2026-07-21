"""
Document upload and ingestion routes (Milestone 3; underlying model renamed
to Resource in Milestone 4 -- see app/models/resource.py).

Scope: upload, list, detail (with processing-job status), retry, file
download, and delete. Ingestion itself (extract -> chunk -> embed -> index)
runs in app/services/ingestion_service.py as a FastAPI BackgroundTask (see
ADR-0005) so the upload request returns immediately with status=QUEUED and
the client polls GET /documents/{id} for progress.

Milestone 4 note: this route's URL prefix (/documents), request/response
schemas (schemas/document.py), and error codes (DOCUMENT_NOT_FOUND,
DUPLICATE_DOCUMENT, DOCUMENT_NOT_FAILED, etc.) are the frozen Milestone 3 API
contract and are deliberately left unchanged -- Milestone 4's approved scope
is the Resource schema + Alembic only, not an API surface change. Every
resource created through this route is content_source=FILE; there is no
route here (or anywhere yet) that creates a CAPTURE resource.

Milestone 5 note (Multi-Format Ingestion): `upload_document` now validates
against the Extractor registry's supported-extension allowlist
(app/services/extraction.py) instead of a hardcoded PDF-only check, and sets
`mime_type` from the real detected format instead of hardcoding
"application/pdf". A new endpoint, `POST /documents/youtube`, accepts a
YouTube URL and creates a resource the same way: it fetches the transcript,
saves it as a plain .txt file through the same storage service, and creates
an ordinary content_source=FILE resource -- there is no second ingestion
pipeline, no new status machine, and no new content_source value (see
app/services/youtube.py and docs/adr/0012-multi-format-extraction.md). Every
other route on this file (list/get/file/delete/retry) is unchanged.

Retrieval, chat, and citations are explicitly out of scope here -- see
Milestone 4 (RAG Chat, per app/README.md's milestone numbering -- unrelated
to "Milestone 4" in the product roadmap sense used elsewhere in this repo).
Nothing in this module reads from the vector store; it only writes to it
(upsert on ingest, delete on document delete).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.deps import AppError, get_current_workspace
from app.models.ingestion_job import IngestionJob
from app.models.resource import Resource, ResourceContentSource, ResourceStatus
from app.models.workspace import Workspace
from app.schemas.document import (
    DocumentDetailOut,
    DocumentListOut,
    DocumentOut,
    IngestionJobOut,
    YoutubeIngestRequest,
)
from app.services.extraction import SUPPORTED_EXTENSIONS, is_supported_filename, mime_type_for
from app.services.ingestion_service import process_document
from app.services.storage import get_storage
from app.services.vector_repo import get_vector_repository
from app.services.youtube import (
    InvalidYoutubeUrlError,
    TranscriptUnavailableError,
    extract_video_id,
    fetch_transcript,
)

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()
_SUPPORTED_EXTENSIONS_LABEL = ", ".join(sorted(SUPPORTED_EXTENSIONS))


def _to_out(resource: Resource) -> DocumentOut:
    return DocumentOut(
        id=resource.id,
        filename=resource.filename or "",
        status=resource.status,
        pageCount=resource.page_count,
        sizeBytes=resource.size_bytes or 0,
        errorMessage=resource.error_message,
        createdAt=resource.created_at.isoformat() if resource.created_at else "",
    )


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for ingestion",
    description=(
        "Accepts a PDF, DOCX, PPTX, TXT/Markdown, a source code file, or an "
        "image (PNG/JPG, run through OCR), up to MAX_UPLOAD_MB. "
        "Returns immediately with status=QUEUED -- extraction, chunking, "
        "embedding, and vector indexing run in the background (see "
        "app/services/ingestion_service.py). Poll GET /documents/{id} for "
        "progress. Rejects unsupported file types (422 UNSUPPORTED_FILE_TYPE), "
        "empty files (422 EMPTY_FILE), oversized files (413 FILE_TOO_LARGE), "
        "and exact re-uploads of a file already in this workspace, by content "
        "checksum (409 DUPLICATE_DOCUMENT)."
    ),
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    if not is_supported_filename(file.filename or ""):
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported file type. Supported extensions: {_SUPPORTED_EXTENSIONS_LABEL}.",
        )

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise AppError(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "FILE_TOO_LARGE",
            f"File exceeds the {settings.MAX_UPLOAD_MB}MB limit.",
        )
    if len(content) == 0:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "EMPTY_FILE", "The uploaded file is empty.")

    storage = get_storage()
    storage_key, checksum = storage.save(workspace.id, file.filename, content)

    existing = (
        db.query(Resource)
        .filter(Resource.workspace_id == workspace.id, Resource.checksum == checksum)
        .first()
    )
    if existing:
        raise AppError(
            status.HTTP_409_CONFLICT, "DUPLICATE_DOCUMENT", "This exact file has already been uploaded."
        )

    resource = Resource(
        workspace_id=workspace.id,
        content_source=ResourceContentSource.FILE,
        filename=file.filename,
        storage_key=storage_key,
        mime_type=mime_type_for(file.filename),
        size_bytes=len(content),
        checksum=checksum,
        status=ResourceStatus.QUEUED,
    )
    db.add(resource)
    db.flush()

    job = IngestionJob(resource_id=resource.id, status="PENDING")
    db.add(job)
    db.commit()

    background_tasks.add_task(_run_ingestion, resource.id)

    return _to_out(resource)


@router.post(
    "/youtube",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a YouTube video's transcript",
    description=(
        "Accepts a youtube.com/youtu.be video URL (422 INVALID_YOUTUBE_URL "
        "for anything else -- this never fetches an arbitrary URL, only the "
        "transcript for a validated video ID). Fetches the transcript (422 "
        "TRANSCRIPT_UNAVAILABLE if the video has none), saves it as a plain "
        "text file, and ingests it through the exact same pipeline as any "
        "other upload -- same status machine, same GET /documents/{id} "
        "polling, same retry/delete routes."
    ),
)
async def ingest_youtube_video(
    background_tasks: BackgroundTasks,
    body: YoutubeIngestRequest,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    try:
        video_id = extract_video_id(body.url)
    except InvalidYoutubeUrlError as exc:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_YOUTUBE_URL", str(exc)) from exc

    try:
        transcript = fetch_transcript(video_id)
    except TranscriptUnavailableError as exc:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "TRANSCRIPT_UNAVAILABLE", str(exc)) from exc

    content = transcript.encode("utf-8")
    filename = f"youtube_{video_id}.txt"

    storage = get_storage()
    storage_key, checksum = storage.save(workspace.id, filename, content)

    existing = (
        db.query(Resource)
        .filter(Resource.workspace_id == workspace.id, Resource.checksum == checksum)
        .first()
    )
    if existing:
        raise AppError(
            status.HTTP_409_CONFLICT,
            "DUPLICATE_DOCUMENT",
            "This video's transcript has already been ingested.",
        )

    resource = Resource(
        workspace_id=workspace.id,
        content_source=ResourceContentSource.FILE,
        filename=filename,
        storage_key=storage_key,
        mime_type="text/plain",
        size_bytes=len(content),
        checksum=checksum,
        status=ResourceStatus.QUEUED,
    )
    db.add(resource)
    db.flush()

    job = IngestionJob(resource_id=resource.id, status="PENDING")
    db.add(job)
    db.commit()

    background_tasks.add_task(_run_ingestion, resource.id)

    return _to_out(resource)


def _run_ingestion(resource_id: str) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        process_document(db, resource_id)
    finally:
        db.close()


@router.get(
    "",
    response_model=DocumentListOut,
    summary="List documents in the current workspace",
    description=(
        "Protected route. Returns only documents belonging to the " "caller's own workspace, newest first."
    ),
)
def list_documents(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    resources = (
        db.query(Resource)
        .filter(Resource.workspace_id == workspace.id)
        .order_by(Resource.created_at.desc())
        .all()
    )
    return DocumentListOut(items=[_to_out(r) for r in resources], nextCursor=None)


@router.get(
    "/{document_id}",
    response_model=DocumentDetailOut,
    summary="Get a document and its processing status",
    description=(
        "Returns 404 DOCUMENT_NOT_FOUND if the document doesn't exist or "
        "belongs to a different workspace -- the two cases are "
        "indistinguishable to the caller, same as every other "
        "workspace-scoped lookup in this API."
    ),
)
def get_document(
    document_id: str,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    resource = db.get(Resource, document_id)
    if not resource or resource.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")

    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.resource_id == document_id)
        .order_by(IngestionJob.id.desc())
        .first()
    )
    job_out = IngestionJobOut(step=job.step, status=job.status, errorCode=job.error_code) if job else None
    return DocumentDetailOut(document=_to_out(resource), processingJob=job_out)


@router.get(
    "/{document_id}/file",
    summary="Download the original PDF",
    description=(
        "Streams the original PDF bytes. Authorized the same way as every "
        "other document route (workspace ownership check) -- there is no "
        "separate signed-URL mechanism in this milestone."
    ),
)
def get_document_file(
    document_id: str,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    resource = db.get(Resource, document_id)
    if not resource or resource.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")

    storage = get_storage()
    path = storage.path_for(resource.storage_key)
    return FileResponse(path, media_type="application/pdf", filename=resource.filename)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description=(
        "Removes the document's DB rows (pages, chunks, ingestion jobs -- "
        "cascade delete), its vector points in Qdrant, and its stored file. "
        "Irreversible."
    ),
)
def delete_document(
    document_id: str,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    resource = db.get(Resource, document_id)
    if not resource or resource.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")

    get_vector_repository().delete_by_document(document_id)
    storage = get_storage()
    try:
        storage.delete(resource.storage_key)
    except OSError:
        pass

    db.delete(resource)
    db.commit()
    return None


@router.post(
    "/{document_id}/retry",
    response_model=DocumentOut,
    summary="Retry a failed document",
    description="Only documents in FAILED status can be retried (409 DOCUMENT_NOT_FAILED otherwise).",
)
def retry_document(
    background_tasks: BackgroundTasks,
    document_id: str,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    resource = db.get(Resource, document_id)
    if not resource or resource.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")
    if resource.status != ResourceStatus.FAILED:
        raise AppError(
            status.HTTP_409_CONFLICT, "DOCUMENT_NOT_FAILED", "Only failed documents can be retried."
        )

    resource.status = ResourceStatus.QUEUED
    resource.error_message = None
    db.commit()
    background_tasks.add_task(_run_ingestion, resource.id)
    return _to_out(resource)
