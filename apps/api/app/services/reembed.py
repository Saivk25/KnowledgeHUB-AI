"""
Re-embed tooling.

Milestone 12 (Section 4.2): given the currently configured
EmbeddingProvider, re-embeds and re-upserts every chunk vector and
concept vector in a workspace, tagging each with the provider's current
`version`. Exists so switching EMBEDDING_PROVIDER or upgrading
OPENAI_EMBEDDING_MODEL has a documented, tested migration path instead of
silently mixing vectors from two different embedding spaces in the same
Qdrant collection (Architecture doc Section 5).

Reuses the exact write paths ingestion/concept-linking already use, and
adds no new VectorRepository method (constraint: reuse the existing
abstractions only, no architecture change):

- Chunks: `ResourceChunk.vector_point_id` is already persisted in
  Postgres (Milestone 3), so re-embedding upserts a fresh vector under
  the *same* point id -- an in-place update via
  `VectorRepository.upsert()`, the identical method
  app/services/ingestion_service.py already calls. Point count is
  unaffected by construction (each upsert replaces exactly one existing
  point).
- Concepts: a Concept's point id is not persisted in Postgres (only its
  `concept_id` is carried as a payload field on the point -- see
  app/services/concept_graph.py). Re-embedding therefore calls
  `VectorRepository.delete_by_concept(concept_id)` (existing since
  Milestone 7) followed by a fresh `upsert()` with a new point id --
  nets to the same point count (one deleted, one added per concept),
  using only methods the interface already exposes.

Selective re-embedding (skip points that already carry the target
version) is implemented for the real Qdrant-backed repository via
`QdrantClient.retrieve()`, called directly on the repository's own
`client` attribute rather than by adding a new VectorRepository method --
this keeps `VectorRepository`'s abstract interface completely unchanged.
The in-memory repository (tests / offline-without-Qdrant only, never
Sai's real deployment) has no equivalent selective path; every point is
simply treated as needing re-embedding there, which is correct, if not
optimized -- there is no real "already up to date" corpus to skip in a
test double.

Batched (`_BATCH_SIZE` per upsert call) and resumable: a partial run
leaves already-processed points correctly re-versioned; re-running skips
whatever the selective check above already finds current. No Postgres
schema change, no migration -- `embedding_model_version` lives entirely
in the vector store's payload.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.concept import Concept, ConceptStatus
from app.models.resource import Resource, ResourceChunk
from app.services.concept_graph import _concept_text
from app.services.embeddings import get_embedding_provider
from app.services.vector_repo import (
    QdrantVectorRepository,
    VectorPoint,
    get_concept_vector_repository,
    get_vector_repository,
    new_point_id,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100


def _stored_versions(vector_repo, point_ids: list[str]) -> dict[str, str]:
    """Best-effort lookup of each point's currently stored
    embedding_model_version, without adding a read method to
    VectorRepository. Only meaningful against the real Qdrant-backed
    repository; returns an empty mapping otherwise (callers treat a
    missing entry as "needs re-embedding")."""
    if not isinstance(vector_repo, QdrantVectorRepository) or not point_ids:
        return {}
    records = vector_repo.client.retrieve(
        collection_name=vector_repo.collection,
        ids=point_ids,
        with_payload=["embedding_model_version"],
        with_vectors=False,
    )
    return {str(r.id): (r.payload or {}).get("embedding_model_version", "") for r in records}


def reembed_chunks(db: Session, workspace_id: str) -> int:
    """Re-embeds every ResourceChunk in `workspace_id` whose stored vector
    doesn't carry the currently configured EmbeddingProvider's version.
    Returns the number of chunks re-embedded."""
    embedder = get_embedding_provider()
    vector_repo = get_vector_repository()

    chunks = (
        db.query(ResourceChunk)
        .join(Resource, ResourceChunk.resource_id == Resource.id)
        .filter(Resource.workspace_id == workspace_id)
        .all()
    )
    if not chunks:
        return 0

    stored = _stored_versions(vector_repo, [c.vector_point_id for c in chunks])
    stale = [c for c in chunks if stored.get(c.vector_point_id, "") != embedder.version]

    reembedded = 0
    for i in range(0, len(stale), _BATCH_SIZE):
        batch = stale[i : i + _BATCH_SIZE]
        vectors = embedder.embed([c.content for c in batch])
        points = [
            VectorPoint(
                id=chunk.vector_point_id,
                vector=vector,
                workspace_id=workspace_id,
                document_id=chunk.resource_id,
                chunk_id=chunk.vector_point_id,
                page_number=chunk.page_number,
                content=chunk.content,
                embedding_model_version=embedder.version,
            )
            for chunk, vector in zip(batch, vectors, strict=False)
        ]
        vector_repo.upsert(points)
        reembedded += len(points)

    if reembedded:
        logger.info(
            "chunks_reembedded workspace_id=%s count=%s version=%s",
            workspace_id,
            reembedded,
            embedder.version,
        )
    return reembedded


def reembed_concepts(db: Session, workspace_id: str) -> int:
    """Re-embeds every active Concept in `workspace_id` whose stored
    vector doesn't carry the currently configured EmbeddingProvider's
    version. Returns the number of concepts re-embedded. Merged concepts
    (ConceptStatus.MERGED) are skipped -- they carry no independent
    evidence and app/services/concept_graph.py never re-derives their
    vector either."""
    embedder = get_embedding_provider()
    concept_repo = get_concept_vector_repository()

    concepts = (
        db.query(Concept)
        .filter(Concept.workspace_id == workspace_id, Concept.status == ConceptStatus.ACTIVE)
        .all()
    )
    if not concepts:
        return 0

    # Concept vector points aren't addressable by a persisted point id
    # (see this module's docstring), so selectivity here is checked via a
    # small per-concept retrieval-by-filter instead of the id-based
    # _stored_versions() helper chunks use. Kept simple and per-concept
    # (not batched into one call) since concept counts are small relative
    # to chunk counts at this product's scale (Architecture Section 5).
    reembedded = 0
    for concept in concepts:
        current_version = _concept_point_version(concept_repo, concept.id)
        if current_version == embedder.version:
            continue

        vector = embedder.embed_one(_concept_text(concept.name, concept.description))
        concept_repo.delete_by_concept(concept.id)
        concept_repo.upsert(
            [
                VectorPoint(
                    id=new_point_id(),
                    vector=vector,
                    workspace_id=workspace_id,
                    concept_id=concept.id,
                    content=_concept_text(concept.name, concept.description),
                    embedding_model_version=embedder.version,
                )
            ]
        )
        reembedded += 1

    if reembedded:
        logger.info(
            "concepts_reembedded workspace_id=%s count=%s version=%s",
            workspace_id,
            reembedded,
            embedder.version,
        )
    return reembedded


def _concept_point_version(concept_repo, concept_id: str) -> str | None:
    """Returns the stored embedding_model_version for a concept's current
    vector point, or None if it can't be determined (in-memory repository,
    or the concept genuinely has no point yet) -- either case is treated
    by the caller as "needs re-embedding"."""
    if not isinstance(concept_repo, QdrantVectorRepository):
        return None
    qm = concept_repo._qm
    hits, _ = concept_repo.client.scroll(
        collection_name=concept_repo.collection,
        scroll_filter=qm.Filter(
            must=[qm.FieldCondition(key="concept_id", match=qm.MatchValue(value=concept_id))]
        ),
        limit=1,
        with_payload=["embedding_model_version"],
        with_vectors=False,
    )
    if not hits:
        return None
    return (hits[0].payload or {}).get("embedding_model_version", "")
