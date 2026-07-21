"""
Document upload and ingestion routes (Milestone 3).

Scope: upload, list, detail (with processing-job status), retry, file
download, and delete. Ingestion itself (extract -> chunk -> embed -> index)
runs in app/services/ingestion_service.py as a FastAPI BackgroundTask (see
ADR-0005) so the upload request returns immediately with status=QUEUED and
the client polls GET /documents/{id} for progress.

Retrieval, chat, and citations are explicitly out of scope here -- see
Milestone 4. Nothing in this module reads from the vector store; it only
writes to it (upsert on ingest, delete on document delete), so Milestone 4
can add a read-only search path without changing anything in this file.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.deps import AppError, get_current_workspace
from app.models.document import Document, DocumentStatus
from app.models.ingestion_job import IngestionJob
from app.models.workspace import Workspace
from app.schemas.document import DocumentDetailOut, DocumentListOut, DocumentOut, IngestionJobOut
from app.services.ingestion_service import process_document
from app.services.storage import get_storage
from app.services.vector_repo import get_vector_repository

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()


def _to_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        filename=document.filename,
        status=document.status,
        pageCount=document.page_count,
        sizeBytes=document.size_bytes,
        errorMessage=document.error_message,
        createdAt=document.created_at.isoformat() if document.created_at else "",
    )


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF for ingestion",
    description=(
        "Accepts a single PDF (application/pdf, up to MAX_UPLOAD_MB). "
        "Returns immediately with status=QUEUED -- extraction, chunking, "
        "embedding, and vector indexing run in the background (see "
        "app/services/ingestion_service.py). Poll GET /documents/{id} for "
        "progress. Rejects non-PDF files (422 UNSUPPORTED_FILE_TYPE), empty "
        "files (422 EMPTY_FILE), oversized files (413 FILE_TOO_LARGE), and "
        "exact re-uploads of a file already in this workspace, by content "
        "checksum (409 DUPLICATE_DOCUMENT)."
    ),
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    if file.content_type not in ("application/pdf",) and not file.filename.lower().endswith(".pdf"):
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "UNSUPPORTED_FILE_TYPE",
            "Only PDF files are supported in this release.",
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
        db.query(Document)
        .filter(Document.workspace_id == workspace.id, Document.checksum == checksum)
        .first()
    )
    if existing:
        raise AppError(
            status.HTTP_409_CONFLICT, "DUPLICATE_DOCUMENT", "This exact file has already been uploaded."
        )

    document = Document(
        workspace_id=workspace.id,
        filename=file.filename,
        storage_key=storage_key,
        mime_type="application/pdf",
        size_bytes=len(content),
        checksum=checksum,
        status=DocumentStatus.QUEUED,
    )
    db.add(document)
    db.flush()

    job = IngestionJob(document_id=document.id, status="PENDING")
    db.add(job)
    db.commit()

    background_tasks.add_task(_run_ingestion, document.id)

    return _to_out(document)


def _run_ingestion(document_id: str) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        process_document(db, document_id)
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
    documents = (
        db.query(Document)
        .filter(Document.workspace_id == workspace.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return DocumentListOut(items=[_to_out(d) for d in documents], nextCursor=None)


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
    document = db.get(Document, document_id)
    if not document or document.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")

    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.id.desc())
        .first()
    )
    job_out = IngestionJobOut(step=job.step, status=job.status, errorCode=job.error_code) if job else None
    return DocumentDetailOut(document=_to_out(document), processingJob=job_out)


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
    document = db.get(Document, document_id)
    if not document or document.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")

    storage = get_storage()
    path = storage.path_for(document.storage_key)
    return FileResponse(path, media_type="application/pdf", filename=document.filename)


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
    document = db.get(Document, document_id)
    if not document or document.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")

    get_vector_repository().delete_by_document(document_id)
    storage = get_storage()
    try:
        storage.delete(document.storage_key)
    except OSError:
        pass

    db.delete(document)
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
    document = db.get(Document, document_id)
    if not document or document.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")
    if document.status != DocumentStatus.FAILED:
        raise AppError(
            status.HTTP_409_CONFLICT, "DOCUMENT_NOT_FAILED", "Only failed documents can be retried."
        )

    document.status = DocumentStatus.QUEUED
    document.error_message = None
    db.commit()
    background_tasks.add_task(_run_ingestion, document.id)
    return _to_out(document)
