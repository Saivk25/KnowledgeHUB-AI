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
    document_id: str
    chunk_id: str
    page_number: int
    content: str


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


def _cosine(a: list[float], b: list[float]) -> float:
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
        scored = [SearchResult(point=p, score=_cosine(query_vector, p.vector)) for p in candidates]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def delete_by_document(self, document_id: str) -> None:
        self._points = {k: v for k, v in self._points.items() if v.document_id != document_id}


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
