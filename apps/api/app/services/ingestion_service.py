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

Milestone 5 update: extraction is no longer a hardcoded PyMuPDF call --
`get_extractor_for(resource.filename)` resolves the right Extractor from the
registry in app/services/extraction.py, so this function does not need to
know or care which of the six supported formats a given resource is.
`ExtractionError` (raised by an extractor on a corrupt/unreadable file) is
caught here and mapped to a FAILED status via `_fail`, the same pattern
already used for SCANNED_PDF_UNSUPPORTED. The `looks_scanned` check remains
PDF-specific -- it means "this PDF has no extractable text, i.e. it is
probably a scanned image" (ADR-0006), a check that doesn't make sense for
any other format. `resource.extraction_confidence` is populated from the
extractor's result for every format, not only OCR (see resource.py).

Milestone 6 update: adds a CLASSIFYING stage between extraction and
chunking (see app/services/classification.py). Classification is
enrichment metadata, not a prerequisite for a resource being usable --
per the approved design, a classifier failure NEVER fails the resource.
It degrades to content_category=OTHER, confidence=0.0, subject=None, a
warning is logged, and the pipeline continues to chunking/embedding/
indexing exactly as if classification had succeeded with a low-confidence
result. `_apply_classification` writes the automatic result to the
`auto_*` columns unconditionally, and to the authoritative/display columns
only if the corresponding `_confirmed` flag is not already set -- a user's
manual correction (via PATCH /documents/{id}/classification) is never
silently overwritten by a later automatic (re)classification, e.g. on retry.

Milestone 7 update: adds a CONCEPT_LINKING stage after indexing (it needs
this resource's chunks and their vectors to already exist -- evidence
links point at a specific chunk, and entity-resolution dedup runs an ANN
search) and before DONE. Same graceful-degradation rule as CLASSIFYING: a
concept-linking failure is logged and never fails the resource -- see
`_link_concepts` below, app/services/concept_linking.py, and
app/services/concept_graph.py. `_link_concepts` replaces (not appends to)
this resource's existing ResourceConcept rows on every run, so a retry
never accumulates stale duplicate evidence links; concept relationships
are deduplicated at write time instead (see `_upsert_relationship`), since
they are not scoped to one resource_id the way evidence links are.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.concept import Concept, ConceptRelationship, ConceptStatus, ResourceConcept
from app.models.ingestion_job import IngestionJob, IngestionStep
from app.models.resource import (
    Resource,
    ResourceChunk,
    ResourceContentCategory,
    ResourcePage,
    ResourceStatus,
    compute_text_hash,
)
from app.services.chunking import chunk_pages
from app.services.classification import Classification, get_classifier
from app.services.concept_graph import find_nearby_concepts, recompute_concept_usage, resolve_concept
from app.services.concept_linking import ChunkRef, RelationshipProposal, get_concept_linker
from app.services.embeddings import get_embedding_provider
from app.services.extraction import ExtractionError, get_extractor_for
from app.services.storage import get_storage
from app.services.vector_repo import VectorPoint, get_vector_repository, new_point_id

logger = logging.getLogger(__name__)
settings = get_settings()


def _apply_classification(resource: Resource, result: Classification) -> None:
    """Writes an automatic classification result onto a resource, per the
    approved Milestone 6 design: `auto_*` fields always reflect the latest
    automatic run (for future evaluation/logging); the authoritative,
    user-facing fields only follow the automatic result until the user
    confirms a correction, after which they are never overwritten
    automatically again."""

    resource.auto_content_category = result.category
    resource.auto_content_category_confidence = result.category_confidence
    resource.auto_subject = result.subject
    resource.auto_subject_confidence = result.subject_confidence

    if not resource.content_category_confirmed:
        resource.content_category = result.category
        resource.content_category_confidence = result.category_confidence
    if not resource.subject_confirmed:
        resource.subject = result.subject
        resource.subject_confidence = result.subject_confidence


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
        file_path = storage.path_for(resource.storage_key)

        extractor = get_extractor_for(resource.filename)
        if extractor is None:
            # Defensive only -- the upload route (and the youtube endpoint,
            # which always saves a .txt file) already validate against the
            # same registry, so this should be unreachable in practice.
            _fail("UNSUPPORTED_FILE_TYPE", "This file type is not supported.")
            return

        try:
            result = extractor.extract(file_path)
        except ExtractionError as exc:
            _fail(exc.code, exc.message)
            return

        if resource.mime_type == "application/pdf" and result.looks_scanned:
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

        # Extraction confidence (Milestone 5) -- see resource.py's field
        # comment. 1.0 for every format except image OCR.
        resource.extraction_confidence = result.confidence
        db.commit()

        if job:
            job.step = IngestionStep.CLASSIFYING
        db.commit()

        try:
            classification = get_classifier().classify(full_text, resource.filename or "")
        except Exception:  # noqa: BLE001
            # Graceful degradation (approved design): classification is
            # enrichment, not a prerequisite -- never fail the resource
            # over this. An honest "we don't know" (OTHER, confidence 0.0)
            # beats either fabricating a category or blocking ingestion.
            logger.warning("classification_failed resource_id=%s", resource.id, exc_info=True)
            classification = Classification(category=ResourceContentCategory.OTHER, category_confidence=0.0)
        _apply_classification(resource, classification)
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

        if job:
            job.step = IngestionStep.CONCEPT_LINKING
        db.commit()

        try:
            _link_concepts(db, resource, chunk_rows)
        except Exception:  # noqa: BLE001
            # Graceful degradation (approved design): concept-linking is
            # enrichment, not a prerequisite -- never fail the resource
            # over this, same rule as classification above.
            logger.warning("concept_linking_failed resource_id=%s", resource.id, exc_info=True)
        db.commit()

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


def _link_concepts(db: Session, resource: Resource, chunk_rows: list[ResourceChunk]) -> None:
    """Milestone 7's CONCEPT_LINKING stage body. See this module's
    docstring for the replace-on-retry / dedup-at-write-time split between
    ResourceConcept and ConceptRelationship."""
    if not chunk_rows:
        return

    previously_linked_concept_ids = {
        rc.concept_id
        for rc in db.query(ResourceConcept).filter(ResourceConcept.resource_id == resource.id).all()
    }
    db.query(ResourceConcept).filter(ResourceConcept.resource_id == resource.id).delete(
        synchronize_session=False
    )
    db.flush()

    chunk_refs = [ChunkRef(id=c.id, content=c.content) for c in chunk_rows]
    nearby = find_nearby_concepts(db, resource.workspace_id, resource.subject or resource.filename or "")

    linker = get_concept_linker()
    result = linker.propose(
        subject=resource.subject,
        subject_confidence=resource.subject_confidence,
        content_category=resource.content_category,
        filename=resource.filename or "",
        chunks=chunk_refs,
        nearby_concepts=nearby,
    )

    newly_linked_concept_ids: set[str] = set()

    if result.concept is not None:
        proposal = result.concept
        concept: Concept | None = None

        if proposal.concept_id is not None:
            candidate = db.get(Concept, proposal.concept_id)
            if candidate is not None and candidate.status == ConceptStatus.ACTIVE:
                concept = candidate
        elif proposal.name:
            resolution = resolve_concept(db, resource.workspace_id, proposal.name, proposal.description)
            concept = resolution.concept

        if concept is not None:
            db.add(
                ResourceConcept(
                    resource_id=resource.id,
                    concept_id=concept.id,
                    confidence=proposal.confidence,
                    contribution_type=proposal.contribution_type,
                    evidence_chunk_id=proposal.evidence_chunk_id,
                )
            )
            newly_linked_concept_ids.add(concept.id)
            db.flush()

            for rel in result.relationships:
                _upsert_relationship(db, resource.workspace_id, concept.id, rel)

    db.flush()
    recompute_concept_usage(db, previously_linked_concept_ids | newly_linked_concept_ids)


def _upsert_relationship(
    db: Session, workspace_id: str, from_concept_id: str, rel: RelationshipProposal
) -> None:
    """Concept relationships are not scoped to one resource_id, so
    idempotency across retries is enforced at write time (skip if an
    equivalent edge already exists) rather than by replacing a resource's
    rows the way `_link_concepts` does for ResourceConcept above."""
    if rel.to_concept_id == from_concept_id:
        return  # no self-loops

    existing = (
        db.query(ConceptRelationship)
        .filter(
            ConceptRelationship.from_concept_id == from_concept_id,
            ConceptRelationship.to_concept_id == rel.to_concept_id,
            ConceptRelationship.relationship_type == rel.relationship_type,
        )
        .first()
    )
    if existing:
        return

    db.add(
        ConceptRelationship(
            workspace_id=workspace_id,
            from_concept_id=from_concept_id,
            to_concept_id=rel.to_concept_id,
            relationship_type=rel.relationship_type,
            strength=rel.strength,
            evidence_chunk_id=rel.evidence_chunk_id,
        )
    )
