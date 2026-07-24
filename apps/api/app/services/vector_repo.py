"""
Vector repository.

Decision: Qdrant as the production vector store, behind a narrow
VectorRepository interface, with an in-memory implementation used for
tests and offline development.

Why Qdrant over pgvector: dedicated vector engine with mature payload
filtering (mandatory workspace_id filter on every query) and a clean path
to hybrid/sparse search later without re-architecting retrieval.
Why Qdrant over Milvus/Weaviate: single-binary Docker deployment with lower
operational overhead, appropriate for a 2-day MVP that still wants a real
production-shaped vector store (see ADR-0002).

Every payload point carries workspace_id + document_id so authorization is
enforced at the retrieval layer, not just the API layer — a document that
is deleted or belongs to another workspace can never be retrieved.

Milestone 7 addition: concept-level embeddings (for entity-resolution
similarity matching, DRR Section 3/11) reuse this exact same
QdrantVectorRepository/InMemoryVectorRepository machinery against a
*second* collection (`settings.QDRANT_CONCEPT_COLLECTION`) rather than a
new store or a dedicated similarity index -- see
`get_concept_vector_repository()` below. `VectorPoint` gains one optional
field, `concept_id`, and every other field gets a default so a concept
point only has to populate what actually applies to it -- the same
"extend the meaning of an existing type rather than fork it" precedent
already used for `page_number` (services/extraction.py) and for
`document_id` itself (this field's own comment, below).

Milestone 12 addition (Section 4.2): `VectorPoint` gains
`embedding_model_version`, stored on every point (both collections) so a
provider/model change is detectable rather than silently mixing two
incompatible embedding spaces together. `QdrantVectorRepository.__init__`
additionally ensures a payload index exists on this field even for a
collection that already existed before this milestone -- see the
defensive `payload_schema` check below, added because whether
`create_payload_index` is safe to call again on an already-indexed field
is not documented one way or the other in the pinned qdrant-client
version this project uses.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VectorPoint:
    id: str
    vector: list[float]
    workspace_id: str
    # VectorPoint/vector_repo.py keep the field name "document_id" for this
    # milestone (see the pre-existing comment on this in
    # ingestion_service.py) -- the value is the Resource's id for chunk
    # points. Given defaults below so a concept point (Milestone 7) can
    # leave this and the following three fields unset rather than filling
    # them with meaningless placeholders.
    document_id: str = ""
    chunk_id: str = ""
    page_number: int = 0
    content: str = ""
    # Milestone 7 only: set for points in the concept-vector collection,
    # None for ordinary chunk points. Kept as a distinct, explicitly-named
    # field (rather than further overloading document_id) since a concept
    # point and a chunk point are never stored in the same collection and
    # code reading a concept point should not have to remember that
    # "document_id" secretly means "concept_id" here.
    concept_id: str | None = None
    # Milestone 12 (Section 4.2): which EmbeddingProvider produced this
    # point's vector (e.g. "local-hash-v1", "openai:text-embedding-3-small").
    # Defaulted to "" (not None) so every existing call site that doesn't
    # pass it explicitly keeps constructing a valid VectorPoint -- additive,
    # not a breaking change to this dataclass's constructor.
    embedding_model_version: str = ""


@dataclass
class SearchResult:
    point: VectorPoint
    score: float


class VectorRepository(ABC):
    @abstractmethod
    def upsert(self, points: list[VectorPoint]) -> None: ...

    @abstractmethod
    def search(self, query_vector: list[float], workspace_id: str, top_k: int) -> list[SearchResult]: ...

    @abstractmethod
    def delete_by_document(self, document_id: str) -> None: ...

    @abstractmethod
    def delete_by_concept(self, concept_id: str) -> None: ...


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Shared cosine-similarity helper. Public (not module-private) as of
    Milestone 8: services/retrieval_service.py needs the identical
    computation to score a concept-expansion candidate that vector search
    itself never returned (see that module's `_build_candidates`) -- it
    imports this rather than reimplementing it, so there is exactly one
    cosine-similarity formula in the codebase, not two that could drift."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5 or 1.0
    norm_b = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (norm_a * norm_b)


class InMemoryVectorRepository(VectorRepository):
    """Used in tests and as a dependency-free fallback if Qdrant is unreachable."""

    def __init__(self):
        self._points: dict[str, VectorPoint] = {}

    def upsert(self, points: list[VectorPoint]) -> None:
        for p in points:
            self._points[p.id] = p

    def search(self, query_vector: list[float], workspace_id: str, top_k: int) -> list[SearchResult]:
        candidates = [p for p in self._points.values() if p.workspace_id == workspace_id]
        scored = [SearchResult(point=p, score=cosine_similarity(query_vector, p.vector)) for p in candidates]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def delete_by_document(self, document_id: str) -> None:
        self._points = {k: v for k, v in self._points.items() if v.document_id != document_id}

    def delete_by_concept(self, concept_id: str) -> None:
        self._points = {k: v for k, v in self._points.items() if v.concept_id != concept_id}


class QdrantVectorRepository(VectorRepository):
    def __init__(self, url: str, collection: str, dimension: int):
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm

        self._qm = qm
        self.collection = collection
        self.client = QdrantClient(url=url)

        existing = [c.name for c in self.client.get_collections().collections]
        if collection not in existing:
            self.client.create_collection(
                collection_name=collection,
                vectors_config=qm.VectorParams(size=dimension, distance=qm.Distance.COSINE),
            )
            self.client.create_payload_index(
                collection_name=collection, field_name="workspace_id", field_schema="keyword"
            )
            self.client.create_payload_index(
                collection_name=collection, field_name="document_id", field_schema="keyword"
            )
            # Milestone 7: harmless on the chunk collection (never queried
            # there); required on the concept collection for
            # delete_by_concept() below.
            self.client.create_payload_index(
                collection_name=collection, field_name="concept_id", field_schema="keyword"
            )
            self.client.create_payload_index(
                collection_name=collection, field_name="embedding_model_version", field_schema="keyword"
            )
        else:
            # Milestone 12 (Section 4.2): a collection created before this
            # milestone (every real deployment's collections, since both
            # `document_chunks_v1` and `concept_vectors_v1` already existed)
            # never got the embedding_model_version index above -- the
            # `if collection not in existing` branch only runs once, at
            # first creation. Checked defensively via payload_schema (not
            # just called unconditionally) because this project's pinned
            # qdrant-client version does not document whether
            # create_payload_index errors or no-ops when the field is
            # already indexed.
            info = self.client.get_collection(collection)
            if "embedding_model_version" not in info.payload_schema:
                self.client.create_payload_index(
                    collection_name=collection, field_name="embedding_model_version", field_schema="keyword"
                )

    def upsert(self, points: list[VectorPoint]) -> None:
        qm = self._qm
        self.client.upsert(
            collection_name=self.collection,
            points=[
                qm.PointStruct(
                    id=p.id,
                    vector=p.vector,
                    payload={
                        "workspace_id": p.workspace_id,
                        "document_id": p.document_id,
                        "chunk_id": p.chunk_id,
                        "page_number": p.page_number,
                        "content": p.content,
                        "concept_id": p.concept_id,
                        "embedding_model_version": p.embedding_model_version,
                    },
                )
                for p in points
            ],
        )

    def search(self, query_vector: list[float], workspace_id: str, top_k: int) -> list[SearchResult]:
        qm = self._qm
        hits = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            query_filter=qm.Filter(
                must=[qm.FieldCondition(key="workspace_id", match=qm.MatchValue(value=workspace_id))]
            ),
            limit=top_k,
        )
        results = []
        for h in hits:
            payload = h.payload or {}
            results.append(
                SearchResult(
                    point=VectorPoint(
                        id=str(h.id),
                        vector=[],
                        workspace_id=payload.get("workspace_id", ""),
                        document_id=payload.get("document_id", ""),
                        chunk_id=payload.get("chunk_id", ""),
                        page_number=payload.get("page_number", 0),
                        content=payload.get("content", ""),
                        concept_id=payload.get("concept_id"),
                        embedding_model_version=payload.get("embedding_model_version", ""),
                    ),
                    score=h.score,
                )
            )
        return results

    def delete_by_document(self, document_id: str) -> None:
        qm = self._qm
        self.client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))]
                )
            ),
        )

    def delete_by_concept(self, concept_id: str) -> None:
        qm = self._qm
        self.client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="concept_id", match=qm.MatchValue(value=concept_id))]
                )
            ),
        )


def new_point_id() -> str:
    return str(uuid.uuid4())


_repo: VectorRepository | None = None


def get_vector_repository() -> VectorRepository:
    """
    Resolves a real Qdrant repository in normal operation. Falls back to an
    in-memory repository if Qdrant is unreachable (e.g. running the API
    without `docker compose up` for a quick unit test) so the rest of the
    app degrades gracefully instead of hard-crashing on import.
    """
    global _repo
    if _repo is not None:
        return _repo
    from app.core.config import get_settings

    settings = get_settings()
    try:
        _repo = QdrantVectorRepository(
            url=settings.QDRANT_URL,
            collection=settings.QDRANT_COLLECTION,
            dimension=settings.EMBEDDING_DIMENSION,
        )
    except Exception:
        _repo = InMemoryVectorRepository()
    return _repo


def set_vector_repository(repo: VectorRepository) -> None:
    """Used by tests to force the in-memory implementation deterministically."""
    global _repo
    _repo = repo


def reset_vector_repository_cache() -> None:
    global _repo
    _repo = None


_concept_repo: VectorRepository | None = None


def get_concept_vector_repository() -> VectorRepository:
    """Milestone 7: same Qdrant deployment, second collection
    (`settings.QDRANT_CONCEPT_COLLECTION`) -- see this module's docstring.
    Falls back to a dedicated in-memory instance under the same
    "degrade gracefully if Qdrant is unreachable" rule as
    get_vector_repository(), and is a genuinely separate cache/instance
    from it so concept vectors and chunk vectors are never accidentally
    mixed even in the in-memory fallback."""
    global _concept_repo
    if _concept_repo is not None:
        return _concept_repo
    from app.core.config import get_settings

    settings = get_settings()
    try:
        _concept_repo = QdrantVectorRepository(
            url=settings.QDRANT_URL,
            collection=settings.QDRANT_CONCEPT_COLLECTION,
            dimension=settings.EMBEDDING_DIMENSION,
        )
    except Exception:
        _concept_repo = InMemoryVectorRepository()
    return _concept_repo


def set_concept_vector_repository(repo: VectorRepository) -> None:
    """Used by tests to force the in-memory implementation deterministically."""
    global _concept_repo
    _concept_repo = repo


def reset_concept_vector_repository_cache() -> None:
    global _concept_repo
    _concept_repo = None
