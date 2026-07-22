"""
Milestone 8: unit tests for the hybrid candidate assembly and
chunk-identity reconciliation in app/services/retrieval_service.py.

These monkeypatch the vector repository and concept lookup so each
candidate's contributing score is exactly known, rather than depending on
LocalHashEmbeddingProvider's emergent hashed-bag-of-words behavior --
that end-to-end behavior (real embeddings, real Qdrant fallback, real
sufficiency outcomes) is covered separately by test_chat_citations.py.
What these tests pin down is the one subtle piece this milestone's design
called out explicitly: a vector-search hit's chunk_id lives in the
ResourceChunk.vector_point_id namespace, never ResourceChunk.id directly,
while a concept-expansion hit's evidence_chunk_id IS a real
ResourceChunk.id -- both must reconcile to the same key so the same
physical chunk is never double-counted, and a concept-match boost is
never missed just because the chunk was also found by vector search.
"""

from dataclasses import dataclass

import pytest

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.concept import Concept, ConceptStatus, ResourceConcept
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.services import retrieval_service
from app.services.embeddings import get_embedding_provider
from app.services.vector_repo import SearchResult, VectorPoint

settings = get_settings()


@dataclass
class _FakeConceptRef:
    id: str
    name: str
    description: str | None = None


class _FakeVectorRepo:
    def __init__(self, hits):
        self._hits = hits

    def search(self, query_vector, workspace_id, top_k):
        return self._hits


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_ready_resource_with_chunk(db, content="Some ready document content."):
    user = User(email="u@example.com", password_hash="x", display_name="U")
    db.add(user)
    db.flush()
    workspace = Workspace(owner_user_id=user.id, name="WS")
    db.add(workspace)
    db.flush()
    resource = Resource(
        workspace_id=workspace.id,
        filename="doc.txt",
        storage_key="k",
        mime_type="text/plain",
        size_bytes=10,
        checksum="c",
        status=ResourceStatus.READY,
    )
    db.add(resource)
    db.flush()
    chunk = ResourceChunk(
        resource_id=resource.id,
        page_number=1,
        chunk_index=0,
        content=content,
        content_hash="h",
        vector_point_id="vp-1",
    )
    db.add(chunk)
    db.flush()
    return workspace, resource, chunk


def _make_concept(db, workspace_id, resource_id, evidence_chunk_id, name="Concept One"):
    concept = Concept(
        workspace_id=workspace_id, name=name, normalized_name=name.lower(), status=ConceptStatus.ACTIVE
    )
    db.add(concept)
    db.flush()
    link = ResourceConcept(
        resource_id=resource_id,
        concept_id=concept.id,
        confidence=0.5,
        contribution_type="MENTIONS",
        evidence_chunk_id=evidence_chunk_id,
    )
    db.add(link)
    db.flush()
    return concept


def test_vector_hit_resolves_to_real_chunk_id_not_vector_point_id(db, monkeypatch):
    """A vector hit's chunk_id (VectorPoint.chunk_id) lives in the
    vector_point_id namespace -- the resolved candidate must be keyed by
    the real ResourceChunk.id, not that raw value."""
    workspace, resource, chunk = _make_ready_resource_with_chunk(db)
    db.commit()

    hit = SearchResult(
        point=VectorPoint(
            id="pt",
            vector=[],
            workspace_id=workspace.id,
            document_id=resource.id,
            chunk_id=chunk.vector_point_id,
            page_number=1,
            content=chunk.content,
        ),
        score=0.9,
    )
    monkeypatch.setattr(retrieval_service, "get_vector_repository", lambda: _FakeVectorRepo([hit]))
    monkeypatch.setattr(retrieval_service, "find_nearby_concepts", lambda *a, **k: [])

    candidates = retrieval_service._build_candidates(
        db, workspace.id, "question", [0.0] * settings.EMBEDDING_DIMENSION, {resource.id}
    )
    assert list(candidates.keys()) == [chunk.id]
    assert candidates[chunk.id].vector_score == 0.9
    assert candidates[chunk.id].from_concept is False


def test_concept_expansion_evidence_dedupes_with_vector_hit_on_same_chunk(db, monkeypatch):
    """A chunk reached via both vector search AND concept expansion must
    be exactly one candidate, boosted -- never double-counted as two."""
    workspace, resource, chunk = _make_ready_resource_with_chunk(db)
    concept = _make_concept(db, workspace.id, resource.id, chunk.id)
    db.commit()

    hit = SearchResult(
        point=VectorPoint(
            id="pt",
            vector=[],
            workspace_id=workspace.id,
            document_id=resource.id,
            chunk_id=chunk.vector_point_id,
            page_number=1,
            content=chunk.content,
        ),
        score=0.2,
    )
    monkeypatch.setattr(retrieval_service, "get_vector_repository", lambda: _FakeVectorRepo([hit]))
    monkeypatch.setattr(
        retrieval_service,
        "find_nearby_concepts",
        lambda *a, **k: [_FakeConceptRef(id=concept.id, name=concept.name)],
    )

    candidates = retrieval_service._build_candidates(
        db, workspace.id, "question", [0.0] * settings.EMBEDDING_DIMENSION, {resource.id}
    )
    assert len(candidates) == 1
    cand = candidates[chunk.id]
    assert cand.from_concept is True
    assert cand.vector_score == 0.2  # concept expansion sets a flag, not a second score

    scored = retrieval_service._score_candidates(db, "question", candidates)
    assert scored[0].final_score == pytest.approx(0.2 + settings.CONCEPT_MATCH_BOOST)


def test_concept_expansion_alone_adds_a_candidate_vector_search_missed(db, monkeypatch):
    """Concept expansion can surface a chunk vector search didn't return
    at all -- it must embed that chunk fresh to get a comparable score,
    never leaving it unscored."""
    workspace, resource, chunk = _make_ready_resource_with_chunk(db, content="unique concept-only content")
    concept = _make_concept(db, workspace.id, resource.id, chunk.id)
    db.commit()

    monkeypatch.setattr(retrieval_service, "get_vector_repository", lambda: _FakeVectorRepo([]))
    monkeypatch.setattr(
        retrieval_service,
        "find_nearby_concepts",
        lambda *a, **k: [_FakeConceptRef(id=concept.id, name=concept.name)],
    )

    query_vector = get_embedding_provider().embed_one("unique concept-only content")
    candidates = retrieval_service._build_candidates(
        db, workspace.id, "question", query_vector, {resource.id}
    )

    assert len(candidates) == 1
    cand = candidates[chunk.id]
    assert cand.from_concept is True
    # Same text embedded twice under the deterministic local provider ->
    # (near-)identical vectors.
    assert cand.vector_score == pytest.approx(1.0, abs=1e-6)


def test_metadata_match_boost_applies_only_when_subject_confirmed_and_overlaps_question(db, monkeypatch):
    workspace, resource, chunk = _make_ready_resource_with_chunk(db)
    resource.subject = "Thermodynamics"
    resource.subject_confirmed = True
    db.commit()

    candidates = {
        chunk.id: retrieval_service._Candidate(
            chunk_id=chunk.id,
            resource_id=resource.id,
            page_number=1,
            content=chunk.content,
            vector_score=0.1,
        )
    }
    scored = retrieval_service._score_candidates(db, "Explain thermodynamics basics", candidates)
    assert scored[0].final_score == pytest.approx(0.1 + settings.METADATA_MATCH_BOOST)

    scored_unrelated = retrieval_service._score_candidates(db, "Explain something else entirely", candidates)
    assert scored_unrelated[0].final_score == pytest.approx(0.1)
