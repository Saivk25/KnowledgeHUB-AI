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

Milestone 4 update: operates on Resource (renamed from Document -- see
app/models/resource.py) and additionally computes `text_hash` once the
resource's full text is known, populating the Resource-level content dedup
field. This does not add a new rejection path (see resource.py's docstring
for why) -- it only makes the column meaningful rather than a dead nullable
field.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ingestion_job import IngestionJob, IngestionStep
from app.models.resource import Resource, ResourceChunk, ResourcePage, ResourceStatus, compute_text_hash
from app.services.chunking import chunk_pages
from app.services.embeddings import get_embedding_provider
from app.services.extraction import extract_text
from app.services.storage import get_storage
from app.services.vector_repo import VectorPoint, get_vector_repository, new_point_id

logger = logging.getLogger(__name__)
settings = get_settings()


def process_document(db: Session, resource_id: str) -> None:
    resource = db.get(Resource, resource_id)
    if resource is None:
        return
    job = db.query(IngestionJob).filter(IngestionJob.resource_id == resource_id).first()

    def _fail(code: str, message: str) -> None:
        resource.status = ResourceStatus.FAILED
        resource.error_message = message
        if job:
            job.status = "FAILED"
            job.step = IngestionStep.FAILED
            job.error_code = code
            job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning("ingestion_failed resource_id=%s code=%s", resource_id, code)

    try:
        resource.status = ResourceStatus.PROCESSING
        if job:
            job.status = "RUNNING"
            job.step = IngestionStep.EXTRACTING
            job.started_at = datetime.now(timezone.utc)
            job.attempt_count += 1
        db.commit()

        storage = get_storage()
        pdf_path = storage.path_for(resource.storage_key)
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
                ResourcePage(
                    resource_id=resource.id,
                    page_number=page_number,
                    text_content=text,
                    char_count=len(text),
                )
            )
        resource.page_count = result.page_count

        # Content-level dedup hash (Milestone 4) -- see resource.py's
        # docstring. Populated here, once the full extracted text is known;
        # not yet used to reject uploads (out of this milestone's scope).
        full_text = "\n".join(text for _, text in result.pages)
        resource.text_hash = compute_text_hash(full_text)
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

        chunk_rows: list[ResourceChunk] = []
        vector_points: list[VectorPoint] = []
        for chunk, vector in zip(chunks, vectors, strict=False):
            point_id = new_point_id()
            chunk_row = ResourceChunk(
                resource_id=resource.id,
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
                    workspace_id=resource.workspace_id,
                    # VectorPoint/vector_repo.py keep the field name
                    # "document_id" for this milestone (the vector store
                    # payload schema/Qdrant collection versioning is
                    # intentionally out of scope -- see
                    # app/services/vector_repo.py). The value is the
                    # Resource's id.
                    document_id=resource.id,
                    chunk_id=point_id,
                    page_number=chunk.page_number,
                    content=chunk.content,
                )
            )

        db.commit()

        vector_repo = get_vector_repository()
        vector_repo.upsert(vector_points)

        resource.status = ResourceStatus.READY
        resource.error_message = None
        if job:
            job.status = "DONE"
            job.step = IngestionStep.DONE
            job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("ingestion_ready resource_id=%s chunks=%s", resource_id, len(chunk_rows))

    except Exception:  # noqa: BLE001
        logger.exception("ingestion_error resource_id=%s", resource_id)
        _fail("INGESTION_ERROR", "An unexpected error occurred while processing this document.")
