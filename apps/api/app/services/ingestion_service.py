"""
Ingestion orchestration: extract -> chunk -> embed -> index.

Decision: run as a FastAPI BackgroundTask for the MVP instead of a
Celery/Temporal worker queue.
Why: it is the smallest moving piece that still makes ingestion
asynchronous (the upload request returns immediately with status=QUEUED,
and the UI polls for progress), which is the behavior the product spec
requires. The service function below has no FastAPI-specific code in its
body, so swapping the caller for a Celery task or Temporal workflow in
Phase 2 does not require rewriting ingestion logic (see ADR-0005).

Milestone note: this module is not imported by app.main in Milestone 1
(Project Foundation) -- it becomes active when the document ingestion
router is mounted in Milestone 3.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document, DocumentChunk, DocumentPage, DocumentStatus
from app.models.ingestion_job import IngestionJob, IngestionStep
from app.services.chunking import chunk_pages
from app.services.embeddings import get_embedding_provider
from app.services.extraction import extract_text
from app.services.storage import get_storage
from app.services.vector_repo import VectorPoint, get_vector_repository, new_point_id

logger = logging.getLogger(__name__)
settings = get_settings()


def process_document(db: Session, document_id: str) -> None:
    document = db.get(Document, document_id)
    if document is None:
        return
    job = db.query(IngestionJob).filter(IngestionJob.document_id == document_id).first()

    def _fail(code: str, message: str) -> None:
        document.status = DocumentStatus.FAILED
        document.error_message = message
        if job:
            job.status = "FAILED"
            job.step = IngestionStep.FAILED
            job.error_code = code
            job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning("ingestion_failed document_id=%s code=%s", document_id, code)

    try:
        document.status = DocumentStatus.PROCESSING
        if job:
            job.status = "RUNNING"
            job.step = IngestionStep.EXTRACTING
            job.started_at = datetime.now(timezone.utc)
            job.attempt_count += 1
        db.commit()

        storage = get_storage()
        pdf_path = storage.path_for(document.storage_key)
        result = extract_text(pdf_path)

        if result.looks_scanned:
            _fail(
                "SCANNED_PDF_UNSUPPORTED",
                "This PDF appears to be a scanned image without extractable text. "
                "OCR support is planned for Phase 2.",
            )
            return

        for page_number, text in result.pages:
            db.add(
                DocumentPage(
                    document_id=document.id,
                    page_number=page_number,
                    text_content=text,
                    char_count=len(text),
                )
            )
        document.page_count = result.page_count
        db.commit()

        if job:
            job.step = IngestionStep.INDEXING
        db.commit()

        chunks = chunk_pages(result.pages)
        if not chunks:
            _fail("NO_EXTRACTABLE_TEXT", "No extractable text was found in this PDF.")
            return

        embedder = get_embedding_provider()
        vectors = embedder.embed([c.content for c in chunks])

        chunk_rows: list[DocumentChunk] = []
        vector_points: list[VectorPoint] = []
        for chunk, vector in zip(chunks, vectors, strict=False):
            point_id = new_point_id()
            chunk_row = DocumentChunk(
                document_id=document.id,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_hash=chunk.content_hash,
                vector_point_id=point_id,
            )
            db.add(chunk_row)
            chunk_rows.append(chunk_row)
            vector_points.append(
                VectorPoint(
                    id=point_id,
                    vector=vector,
                    workspace_id=document.workspace_id,
                    document_id=document.id,
                    chunk_id=point_id,
                    page_number=chunk.page_number,
                    content=chunk.content,
                )
            )

        db.commit()

        vector_repo = get_vector_repository()
        vector_repo.upsert(vector_points)

        document.status = DocumentStatus.READY
        document.error_message = None
        if job:
            job.status = "DONE"
            job.step = IngestionStep.DONE
            job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("ingestion_ready document_id=%s chunks=%s", document_id, len(chunk_rows))

    except Exception:  # noqa: BLE001
        logger.exception("ingestion_error document_id=%s", document_id)
        _fail("INGESTION_ERROR", "An unexpected error occurred while processing this document.")
