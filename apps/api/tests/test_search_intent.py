"""
Milestone 9: unit tests for app/services/intents/search.py -- SearchIntent
always returns ranked hits regardless of confidence, and only calls the
LLM when the top score is below SEARCH_LLM_CONFIDENCE_THRESHOLD (approved
design, MILESTONE_9.md Section 4 decision 3 -- your explicit direction,
not the original "never call an LLM" recommendation).
"""

import pytest

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.intents import IntentRequest
from app.services import retrieval_service
from app.services.intents.search import SearchIntent
from app.services.vector_repo import SearchResult as VectorSearchResult
from app.services.vector_repo import VectorPoint

settings = get_settings()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class _FakeVectorRepo:
    def __init__(self, hits):
        self._hits = hits

    def search(self, query_vector, workspace_id, top_k):
        return self._hits


class _SpyLLMProvider:
    name = "spy"

    def __init__(self):
        self.call_count = 0

    def answer(self, question, evidence):
        self.call_count += 1
        return "synthesized answer [1]"

    def answer_general_knowledge(self, question):
        raise AssertionError("Search must never call answer_general_knowledge")

    def summarize(self, target_label, evidence):
        raise AssertionError("not used by SearchIntent")

    def compare(self, targets):
        raise AssertionError("not used by SearchIntent")


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


def _hit_for(workspace_id, resource_id, chunk, score):
    return VectorSearchResult(
        point=VectorPoint(
            id="pt",
            vector=[],
            workspace_id=workspace_id,
            document_id=resource_id,
            chunk_id=chunk.vector_point_id,
            page_number=chunk.page_number,
            content=chunk.content,
        ),
        score=score,
    )


def test_confident_match_returns_hits_without_calling_llm(db, monkeypatch):
    workspace, resource, chunk = _make_ready_resource_with_chunk(db)
    db.commit()

    # A strong single hit clears SUFFICIENCY_STRONG_SCORE, so
    # compute_sufficiency reports it unhalved -- comfortably above
    # SEARCH_LLM_CONFIDENCE_THRESHOLD.
    hit = _hit_for(workspace.id, resource.id, chunk, settings.SUFFICIENCY_STRONG_SCORE + 0.1)
    monkeypatch.setattr(retrieval_service, "get_vector_repository", lambda: _FakeVectorRepo([hit]))
    monkeypatch.setattr(retrieval_service, "find_nearby_concepts", lambda *a, **k: [])
    spy = _SpyLLMProvider()
    monkeypatch.setattr("app.services.intents.search.get_llm_provider", lambda: spy)

    response = SearchIntent().handle(db, workspace, IntentRequest(intent="SEARCH", question="ready document"))

    assert response.result.kind == "search"
    assert len(response.result.hits) == 1
    assert response.result.assistedSynthesis is None
    assert spy.call_count == 0
    assert response.provenance == "LOCAL"
    assert response.status == "OK"


def test_low_confidence_match_adds_grounded_synthesis(db, monkeypatch):
    workspace, resource, chunk = _make_ready_resource_with_chunk(db)
    db.commit()

    # A lone mediocre hit: compute_sufficiency halves it for lacking
    # corroboration, landing well below SEARCH_LLM_CONFIDENCE_THRESHOLD.
    hit = _hit_for(workspace.id, resource.id, chunk, 0.25)
    monkeypatch.setattr(retrieval_service, "get_vector_repository", lambda: _FakeVectorRepo([hit]))
    monkeypatch.setattr(retrieval_service, "find_nearby_concepts", lambda *a, **k: [])
    spy = _SpyLLMProvider()
    monkeypatch.setattr("app.services.intents.search.get_llm_provider", lambda: spy)

    response = SearchIntent().handle(db, workspace, IntentRequest(intent="SEARCH", question="ready document"))

    assert len(response.result.hits) == 1
    assert response.result.assistedSynthesis is not None
    assert spy.call_count == 1
    assert response.provenance == "LOCAL"


def test_no_candidates_returns_empty_honest_result_without_llm(db, monkeypatch):
    workspace, resource, chunk = _make_ready_resource_with_chunk(db)
    db.commit()

    monkeypatch.setattr(retrieval_service, "get_vector_repository", lambda: _FakeVectorRepo([]))
    monkeypatch.setattr(retrieval_service, "find_nearby_concepts", lambda *a, **k: [])
    spy = _SpyLLMProvider()
    monkeypatch.setattr("app.services.intents.search.get_llm_provider", lambda: spy)

    response = SearchIntent().handle(
        db, workspace, IntentRequest(intent="SEARCH", question="nothing matches")
    )

    assert response.status == "INSUFFICIENT"
    assert response.result.hits == []
    assert response.result.assistedSynthesis is None
    assert spy.call_count == 0
    assert response.provenance is None
