"""
Milestone 9: unit tests for app/services/intents/summarize.py's three
modes -- resource-target, concept-target, and freeform-question (which
goes through the same hybrid retrieval + real sufficiency gate EXPLAIN
uses, so FR-10 applies identically -- see the adversarial test below).
"""

import pytest

from app.db.session import SessionLocal
from app.deps import AppError
from app.models.concept import Concept, ConceptStatus, ResourceConcept
from app.models.resource import Resource, ResourceChunk, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.intents import IntentRequest
from app.services import retrieval_service
from app.services.intents.summarize import SummarizeIntent


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class _StubLLMProvider:
    name = "stub"

    def answer(self, question, evidence):
        return "n/a"

    def answer_general_knowledge(self, question):
        return "n/a"

    def summarize(self, target_label, evidence):
        return f"Summary of {target_label} citing " + ", ".join(f"[{e.order}]" for e in evidence)

    def compare(self, targets):
        return "n/a"


class _EmptyVectorRepo:
    def search(self, query_vector, workspace_id, top_k):
        return []


def _make_workspace_and_resource(db, content="Some content to summarize."):
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


def test_resource_target_summarizes_all_chunks(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr("app.services.intents.summarize.get_llm_provider", lambda: _StubLLMProvider())

    response = SummarizeIntent().handle(
        db, workspace, IntentRequest(intent="SUMMARIZE", resourceId=resource.id)
    )

    assert response.status == "OK"
    assert response.provenance == "LOCAL"
    assert response.result.kind == "summarize"
    assert response.result.target == "doc.txt"
    assert "[1]" in response.result.content
    assert len(response.citations) == 1


def test_concept_target_summarizes_all_evidence(db, monkeypatch):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    concept = Concept(
        workspace_id=workspace.id,
        name="Gradient Descent",
        normalized_name="gradient descent",
        status=ConceptStatus.ACTIVE,
    )
    db.add(concept)
    db.flush()
    link = ResourceConcept(
        resource_id=resource.id,
        concept_id=concept.id,
        confidence=0.9,
        contribution_type="DEFINES",
        evidence_chunk_id=chunk.id,
    )
    db.add(link)
    db.commit()
    monkeypatch.setattr("app.services.intents.summarize.get_llm_provider", lambda: _StubLLMProvider())

    response = SummarizeIntent().handle(
        db, workspace, IntentRequest(intent="SUMMARIZE", conceptId=concept.id)
    )

    assert response.status == "OK"
    assert response.result.target == "Gradient Descent"
    assert len(response.citations) == 1


def test_freeform_summarize_with_zero_local_coverage_is_never_labeled_local(db, monkeypatch):
    """FR-10-style adversarial case, applied to Summarize's freeform mode."""
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    monkeypatch.setattr(retrieval_service, "get_vector_repository", lambda: _EmptyVectorRepo())
    monkeypatch.setattr(retrieval_service, "find_nearby_concepts", lambda *a, **k: [])

    response = SummarizeIntent().handle(
        db, workspace, IntentRequest(intent="SUMMARIZE", question="something with zero coverage")
    )

    assert response.status == "INSUFFICIENT"
    assert response.provenance is None


def test_resource_not_found_raises_error(db):
    workspace, resource, chunk = _make_workspace_and_resource(db)
    db.commit()
    with pytest.raises(AppError):
        SummarizeIntent().handle(db, workspace, IntentRequest(intent="SUMMARIZE", resourceId="nonexistent"))
